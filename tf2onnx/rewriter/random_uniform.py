# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT license.

"""
tf2onnx.rewrite - rewrite tensorflow subgraph to onnx random_uniform op
"""
from onnx import helper, onnx_pb, numpy_helper
from tf2onnx.graph import Node, Graph
from tf2onnx.graph_matcher import OpTypePattern, GraphMatcher
from tf2onnx import utils
from tf2onnx.utils import port_name

def rewrite_random_uniform(g, ops):
    pattern = \
        OpTypePattern('Add', name='output', inputs=[
            OpTypePattern('Mul', inputs=[
                OpTypePattern('RandomUniform', name='input1', inputs=["*"]),
                OpTypePattern('Sub', name='input2', inputs=["*", "*"]),
            ]), None
        ])

    matcher = GraphMatcher(pattern)
    match_results = list(matcher.match_ops(ops))
    for match in match_results:
        input2 = match.get_op('input2')
        output = match.get_op('output')
        ru_op = match.get_op('input1')
        # max is on input 0
        tmax = input2.inputs[0].get_tensor_value()[0]
        tmin = input2.inputs[1].get_tensor_value()[0]
        dtype = output.dtype
        new_node = create_onnx_random_uniform_op(g, tmax, tmin, ru_op, output)
        ops = g.replace_subgraph(ops, match, [], [output], [], [new_node])

    return ops

# rewriter function when fold_const is enabled
def rewrite_random_uniform_fold_const(g, ops):
    pattern = \
        OpTypePattern('Add', name='output', inputs=[
            OpTypePattern('Mul', name='mul', inputs=[
                OpTypePattern('RandomUniform', name='input1', inputs=["*"]),
                None,
            ]),
            None,
        ])

    matcher = GraphMatcher(pattern)
    match_results = list(matcher.match_ops(ops))
    for match in match_results:
        output = match.get_op('output')
        mul = match.get_op('mul')
        ru_op = match.get_op('input1')

        tmax_minus_tmin = mul.inputs[1].get_tensor_value()[0]
        tmin = output.inputs[1].get_tensor_value()[0]
        tmax = tmin + tmax_minus_tmin
        new_node = create_onnx_random_uniform_op(g, tmax, tmin, ru_op, output)
        ops = g.replace_subgraph(ops, match, [], [output], [], [new_node])

    return ops

def create_onnx_random_uniform_op(g, tmax, tmin, ru_op, output):
    dtype = output.dtype
    op_name = utils.make_name("RandomUniform")
    out_name = port_name(op_name)
    if ru_op.inputs[0].type == "Shape":
        shape_node = ru_op.inputs[0]
        new_node = Node(helper.make_node("RandomUniformLike",
                                            [shape_node.input[0]], [out_name], name=op_name,
                                            low=tmin, high=tmax, dtype=dtype), g)
    else:
        shape = g.get_shape(output.output[0])
        new_node = Node(helper.make_node("RandomUniform",
                                            [], [out_name], name=op_name,
                                            low=tmin, high=tmax, dtype=dtype, shape=shape), g)
    return new_node