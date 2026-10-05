# SPDX-License-Identifier: GPL-3.0-only
"""Approved image-resident arithmetic/Boolean interpreter and OCR consensus.

This source is authored here but execution loads these exact bytes from pixels.
It has no image, file, network, process, or user-interface operations.
"""
import ast
import math
import operator

class Rejected(ValueError):
    pass

def parse_expression(text):
    if not isinstance(text, str) or not 0 < len(text) <= 200 or not text.isascii():
        raise Rejected("Expression must contain 1..200 ASCII characters")
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise Rejected("OCR did not produce a valid expression") from exc
    if len(list(ast.walk(tree))) > 64:
        raise Rejected("Expression complexity limit")
    binary = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
              ast.Div: operator.truediv, ast.Mod: operator.mod}
    compare = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
               ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}
    def visit(node, depth=0):
        if depth > 16:
            raise Rejected("Expression depth limit")
        child = lambda value: visit(value, depth + 1)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float, bool):
            result = node.value
        elif isinstance(node, ast.BinOp) and type(node.op) in binary:
            try:
                result = binary[type(node.op)](child(node.left), child(node.right))
            except (ZeroDivisionError, OverflowError) as exc:
                raise Rejected("Undefined arithmetic") from exc
        elif isinstance(node, ast.UnaryOp) and type(node.op) in (ast.UAdd, ast.USub, ast.Not):
            result = {ast.UAdd: operator.pos, ast.USub: operator.neg, ast.Not: operator.not_}[type(node.op)](child(node.operand))
        elif isinstance(node, ast.BoolOp) and type(node.op) in (ast.And, ast.Or):
            values = [bool(child(value)) for value in node.values]
            result = all(values) if isinstance(node.op, ast.And) else any(values)
        elif isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in compare:
            result = compare[type(node.ops[0])](child(node.left), child(node.comparators[0]))
        else:
            raise Rejected("Expression contains an unsupported operation")
        if type(result) not in (bool, int, float) or abs(result) > 1e12 or not math.isfinite(result):
            raise Rejected("Numeric range exceeded")
        return result
    return tree, visit(tree.body)


def safe_expression(text):
    return parse_expression(text)[1]


def select_ocr_expressions(recognized):
    if not isinstance(recognized, dict):
        raise Rejected("Invalid OCR evidence object")
    def parse_lines(text):
        if not isinstance(text, str) or len(text) > 2048:
            raise Rejected("OCR text length limit")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not 1 <= len(lines) <= 6:
            raise Rejected("OCR must provide 1..6 nonempty expressions")
        parsed = [parse_expression(line) for line in lines]
        return lines, [ast.dump(tree, include_attributes=False) for tree, _ in parsed], [value for _, value in parsed]
    lines, meaning, values = parse_lines(recognized.get("text"))
    passes = recognized.get("passes")
    if not isinstance(passes, list) or len(passes) not in (3, 6):
        raise Rejected("Three or six independent OCR passes are required")
    numbers, profiles = set(), set()
    for item in passes:
        if not isinstance(item, dict) or type(item.get("pass_number")) is not int:
            raise Rejected("Invalid OCR pass evidence")
        profile_info = item.get("profile")
        if not isinstance(profile_info, dict):
            raise Rejected("Invalid OCR profile evidence")
        number, profile = item["pass_number"], profile_info.get("profile_id")
        if number in numbers or not isinstance(profile, str) or not profile or profile in profiles:
            raise Rejected("Duplicated or missing OCR pass identity")
        numbers.add(number); profiles.add(profile)
        if parse_lines(item.get("text"))[1] != meaning:
            raise Rejected("OCR passes disagree on expression structure; computation withheld")
    if numbers != set(range(1, len(passes) + 1)):
        raise Rejected("OCR pass sequence is incomplete")
    geometry = recognized.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("passed") is not True:
        raise Rejected("OCR token geometry did not pass validation")
    return lines, values, {"agreeing_passes": len(passes), "rule": "all pass AST structures agree",
                          "upstream_manual_review_required": bool(recognized.get("manual_review_required", True)),
                          "scope": "agreement is not independent proof of OCR accuracy"}


