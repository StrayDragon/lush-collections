"""lush-dal-protocol 下游类型检查示例.

本模块展示下游用户如何正确使用 lush-dal-protocol 的类型,
作为 typecheck SSOT (Single Source of Truth).

如果库的类型变更导致这些示例无法通过 basedpyright 检查,
说明可能破坏了下游合法用法.

示例场景:
1. example_01_dto.py — 使用 BaseCU/BaseDTO 创建自定义 DTO
2. example_02_pagination.py — 使用分页类型
3. example_04_protocol_only.py — 仅使用协议类型 (不依赖具体 ORM)
"""
