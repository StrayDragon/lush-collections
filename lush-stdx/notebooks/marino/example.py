import marimo

__generated_with = "0.18.4"
app = marimo.App()


@app.cell
def _():
    from pydantic import BaseModel, ValidationError

    from lush_stdx.enumx import EnumField, MetaInfoIntEnum, MetaInfoStrEnum, XMetaInfo

    class OrderStatus(MetaInfoIntEnum):
        PENDING_PAYMENT = (10, XMetaInfo(description="待支付"))
        PROCESSING = (20, XMetaInfo(description="处理中"))
        SHIPPED = (30, XMetaInfo(description="已发货"))
        COMPLETED = (40, XMetaInfo(description="已完成"))
        CANCELLED = (99, XMetaInfo(description="已取消"))

    class UserRole(MetaInfoStrEnum):
        ADMIN = ("admin", XMetaInfo(description="管理员"))
        EDITOR = ("editor", XMetaInfo(description="编辑"))
        VIEWER = ("viewer", XMetaInfo(description="查看者"))

    class PlainOrder:
        status = EnumField(OrderStatus)

        def __init__(self, order_id: str, initial_status: OrderStatus = OrderStatus.PENDING_PAYMENT):
            self.order_id = order_id
            self.status = initial_status

        def display(self):
            if self.status:
                print(f"订单 [ID: {self.order_id}] | 状态: {self.status.x_meta.description} (代码: {self.status.value})")
            else:
                print(f"订单 [ID: {self.order_id}] | 状态: 未设置")

    class PydanticOrder(BaseModel):
        order_id: str
        status: OrderStatus

        def display(self):
            print(f"Pydantic 订单 [ID: {self.order_id}] | 状态: {self.status.x_meta.description} (代码: {self.status.value})")

    class PydanticUser(BaseModel):
        username: str
        role: UserRole

        def display(self):
            print(f"Pydantic 用户 [Username: {self.username}] | 角色: {self.role.x_meta.description} (值: '{self.role.value}')")

    return (
        OrderStatus,
        PlainOrder,
        PydanticOrder,
        PydanticUser,
        UserRole,
        ValidationError,
    )


@app.cell
def _(
    OrderStatus,
    PlainOrder,
    PydanticOrder,
    PydanticUser,
    UserRole,
    ValidationError,
):
    def run_tests():
        print("=" * 60)
        print("🚀 开始执行测试套件...")
        print("=" * 60)

        run_int_enum_tests()
        run_str_enum_tests()

        print("=" * 60)
        print("🎉 所有测试均已成功通过!")
        print("=" * 60)

    def run_int_enum_tests():
        print("\n" + "-" * 20 + " INT ENUM TESTS " + "-" * 20)
        print("\n--- 1. 测试核心 IntEnum 定义 ---")
        status_member = OrderStatus.PROCESSING
        print(f"获取的成员 (repr): {status_member!r}")
        assert isinstance(status_member, int)
        print(f"成员是 int 的实例: {isinstance(status_member, int)}")
        assert status_member == 20
        assert status_member.x_meta.description == "处理中"  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
        print(f"成员的描述: '{status_member.x_meta.description}'")  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
        assert OrderStatus(10) == OrderStatus.PENDING_PAYMENT
        print("✅ IntEnum 定义测试通过!")

        print("\n--- 2. 测试 PlainOrder (带描述符) ---")
        order1 = PlainOrder("PO-001")
        order1.display()
        assert order1.status == OrderStatus.PENDING_PAYMENT
        print("  -> 通过整数 30 更新状态...")
        order1.status = 30
        order1.display()
        assert order1.status == OrderStatus.SHIPPED
        print("✅ PlainOrder 测试通过!")

        print("\n--- 3. 测试 PydanticOrder (Pydantic 模型) ---")
        p_order1_data = {"order_id": "PDO-001", "status": 20}
        p_order1 = PydanticOrder.model_validate(p_order1_data)
        print(f"  -> 从数据 {p_order1_data} 创建模型:")
        p_order1.display()
        assert isinstance(p_order1.status, OrderStatus)
        assert p_order1.status == OrderStatus.PROCESSING
        dumped_data = p_order1.model_dump()
        print(f"  -> 模型序列化 (model_dump): {dumped_data}")
        assert dumped_data["status"] == 20
        print("✅ PydanticOrder 测试通过!")

        print("\n--- 4. 测试 IntEnum OpenAPI Schema 生成 ---")
        schema = PydanticOrder.model_json_schema()
        status_schema = schema["properties"]["status"]
        print("  -> 生成的 PydanticOrder Schema 中 'status' 字段的部分内容:")
        import json

        print(json.dumps(status_schema, indent=2, ensure_ascii=False))
        assert "枚举值" in status_schema["description"]
        assert "* `10`: 待支付" in status_schema["description"]
        assert status_schema["enum"] == [10, 20, 30, 40, 99]
        print("✅ IntEnum OpenAPI Schema 测试通过!")

    def run_str_enum_tests():
        print("\n" + "-" * 20 + " STR ENUM TESTS " + "-" * 20)
        print("\n--- 1. 测试核心 StrEnum 定义 ---")
        role_member = UserRole.ADMIN
        print(f"获取的成员 (repr): {role_member!r}")
        assert isinstance(role_member, str)
        print(f"成员是 str 的实例: {isinstance(role_member, str)}")
        assert role_member == "admin"
        assert role_member.x_meta.description == "管理员"  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
        print(f"成员的描述: '{role_member.x_meta.description}'")  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
        assert UserRole("editor") == UserRole.EDITOR
        print("✅ StrEnum 定义测试通过!")

        print("\n--- 2. 测试 PydanticUser (Pydantic 模型) ---")
        p_user1_data = {"username": "testuser", "role": "editor"}
        p_user1 = PydanticUser.model_validate(p_user1_data)
        print(f"  -> 从数据 {p_user1_data} 创建模型:")
        p_user1.display()
        assert isinstance(p_user1.role, UserRole)
        assert p_user1.role == UserRole.EDITOR

        p_user2_data = {"username": "testuser2", "role": UserRole.VIEWER}
        p_user2 = PydanticUser.model_validate(p_user2_data)
        print(f"  -> 从数据 {p_user2_data} 创建模型:")
        p_user2.display()
        assert p_user2.role == "viewer"

        dumped_data = p_user1.model_dump()
        print(f"  -> 模型序列化 (model_dump): {dumped_data}")
        assert dumped_data["role"] == "editor"
        assert isinstance(dumped_data["role"], str)

        invalid_data = {"username": "failuser", "role": "guest"}
        try:
            print(f"  -> 尝试使用无效数据 {invalid_data} 创建模型...")
            _ = PydanticUser.model_validate(invalid_data)
        except ValidationError as e:
            print("  👍 成功捕获到 Pydantic 验证错误!")
            assert "'guest' is not a valid value or name for UserRole" in str(e)
        print("✅ PydanticUser 测试通过!")

        print("\n--- 3. 测试 StrEnum OpenAPI Schema 生成 ---")
        schema = PydanticUser.model_json_schema()
        role_schema = schema["properties"]["role"]
        print("  -> 生成的 PydanticUser Schema 中 'role' 字段的部分内容:")
        import json

        print(json.dumps(role_schema, indent=2, ensure_ascii=False))
        assert "枚举值" in role_schema["description"]
        assert "* `admin`: 管理员" in role_schema["description"]
        assert role_schema["enum"] == ["admin", "editor", "viewer"]
        print("✅ StrEnum OpenAPI Schema 测试通过!")

    return (run_tests,)


@app.cell
def _(run_tests):
    run_tests()


if __name__ == "__main__":
    app.run()
