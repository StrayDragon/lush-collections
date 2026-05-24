# RFC: lush-dal-protocol 演进规划

> Status: Phase 1–4 IMPLEMENTED, Phase 5 PLANNED  
> Created: 2026-05-24  
> Affects: `lush-dal-protocol`, `lush-sqlalchemyx`, 未来 `lush-djangox`, `lush-peeweex`, `lush-tortoisex`

## 目标

将 `lush-dal-protocol` 打造为 **Python ORM 无关的通用 DAL 协议层**，使同一套业务代码可以在 SQLAlchemy / Django ORM / Peewee / TortoiseORM 之间切换，且心智负担趋近于零。

---

## Phase 1: PrimaryKeyT 泛型化 (Breaking)

### 现状

所有 ABC 方法硬编码 `entity_id: int`，不支持 UUID / str / 复合主键。

### 方案

```python
# abc/_types.py
from typing_extensions import TypeVar

SessionT = TypeVar("SessionT")
EntityT = TypeVar("EntityT")
PrimaryKeyT = TypeVar("PrimaryKeyT", default=int)  # 默认 int，兼容现有用户
```

#### ABC 签名变更示例

```python
class AbstractSyncReadDAL(ABC, Generic[SessionT, EntityT, DTOModelT, PrimaryKeyT, ExtraT]):
    @classmethod
    @abstractmethod
    def get_by_id(cls, session: SessionT, entity_id: PrimaryKeyT, extra: ExtraT | None = None) -> EntityT | None: ...

    @classmethod
    @abstractmethod
    def exists(cls, session: SessionT, entity_id: PrimaryKeyT, extra: ExtraT | None = None) -> bool: ...

    @classmethod
    @abstractmethod
    def batch_get_id__entity(cls, session: SessionT, entity_ids: Iterable[PrimaryKeyT], extra: ExtraT | None = None) -> dict[PrimaryKeyT, EntityT]: ...
```

#### 迁移策略

- `PrimaryKeyT` 使用 `default=int` (PEP 696)，现有不指定该参数的代码无需改动。
- `lush-sqlalchemyx` 继续绑定为 `int` 不受影响。
- 新增的 Django/Peewee adapter 可绑定 `UUID | int | str`。

#### 影响范围

| 文件 | 变更类型 |
|------|---------|
| `abc/_types.py` | 新增 `PrimaryKeyT` |
| `abc/read.py` | Generic 参数 + 签名 |
| `abc/write.py` | Generic 参数 + 签名 |
| `abc/lock.py` | Generic 参数 + 签名 |
| `abc/advanced_write.py` | Generic 参数 + 签名 |
| `abc/composed.py` | Generic 参数 |
| `testing/conformance.py` | fixture 类型 + helper |
| `testing/reference.py` | 实体 id 类型 |
| `lush-sqlalchemyx` V2 | 泛型参数追加 `int` |

---

## Phase 2: SessionlessDAL 变体 (Non-Breaking, Additive)

### 动机

Django ORM / Peewee / TortoiseORM 没有显式 session 概念：

| ORM | Session 等价物 | 事务控制 |
|-----|---------------|---------|
| SQLAlchemy | `Session` / `AsyncSession` | `session.commit()` |
| Django | 无 (connection 自动管理) | `@transaction.atomic` |
| Peewee | `Database` context | `db.atomic()` |
| TortoiseORM | 无 (全局连接池) | `@atomic()` |

### 方案

新增 `abc/sessionless.py`，定义无 session 参数的 ABC 变体：

```python
# abc/sessionless.py
class AbstractSyncSessionlessReadDAL(ABC, Generic[EntityT, DTOModelT, PrimaryKeyT, ExtraT]):
    """无显式 session 的同步只读 DAL.

    适用于 Django ORM / Peewee 等由框架自动管理连接的 ORM.
    """

    @classmethod
    @abstractmethod
    def get_by_id(cls, entity_id: PrimaryKeyT, extra: ExtraT | None = None) -> EntityT | None: ...

    @classmethod
    @abstractmethod
    def get_all(cls, skip: int = 0, limit: int = 100, extra: ExtraT | None = None) -> list[DTOModelT]: ...

    @classmethod
    @abstractmethod
    def count(cls, extra: ExtraT | None = None) -> int: ...

    @classmethod
    @abstractmethod
    def exists(cls, entity_id: PrimaryKeyT, extra: ExtraT | None = None) -> bool: ...

    # ... 与 SessionDAL 一一对应, 仅去掉 session 参数
```

#### 适配器桥接

为已有 session-based DAL 提供自动桥接：

```python
# adapters/bridge.py
class SessionBridge(Generic[SessionT]):
    """将 sessionless 调用桥接到 session-based DAL."""

    def __init__(self, session_factory: Callable[[], ContextManager[SessionT]]):
        self._session_factory = session_factory

    def wrap(self, dal_class: type[AbstractSyncBaseDAL]) -> type[AbstractSyncSessionlessReadDAL]:
        """运行时生成 sessionless 包装类."""
        ...
```

#### Django 适配示例

```python
# lush-djangox (未来)
from lush_dal_protocol.abc.sessionless import AbstractSyncSessionlessBaseDAL

class DjangoBaseDAL(AbstractSyncSessionlessBaseDAL[DjangoModel, DTOModelT, PrimaryKeyT, DjangoExtra]):
    _Model: ClassVar[type[Model]]
    _DTO: ClassVar[type[DTOModelT]]

    @classmethod
    def get_by_id(cls, entity_id: PrimaryKeyT, extra: DjangoExtra | None = None) -> DjangoModel | None:
        try:
            return cls._Model.objects.get(pk=entity_id)
        except cls._Model.DoesNotExist:
            return None

    @classmethod
    def create(cls, cu: CUModelT, extra: DjangoExtra | None = None) -> DjangoModel:
        data = cu.model_dump(exclude_unset=True, exclude={"id"})
        return cls._Model.objects.create(**data)
```

#### 一致性测试复用

Conformance 套件通过 fixture 适配两种风格：

```python
# 对于 sessionless DAL，fixture 返回 None session，conformance 测试中的 session 参数被 adapter 忽略
class SessionlessConformanceAdapter:
    """将 sessionless DAL 包装为 session-based 接口以复用 conformance 测试."""
    ...
```

---

## Phase 3: lush-sqlalchemyx V1 日落 (Breaking)

### 现状

- V1 (`_async.py` / `_sync.py`): ~1900 行原始实现
- V2 (`_async_v2.py` / `_sync_v2.py`): ~370 行 ABC 适配层，继承 V1 + ABC
- 问题：双轨维护成本高，`pyright: ignore[reportIncompatibleMethodOverride]` 散落

### 合并策略

```
阶段 A: V2 成为推荐入口 (当前版本 0.2.x)
  └─ V1 类标记 @deprecated, 文档指向 V2
  └─ 发布 0.3.0

阶段 B: V1 API 移入 _legacy.py (0.4.x)
  └─ V1 classmethod 变为 V2 的 thin alias
  └─ 不同签名的方法 (无 extra) 保留为兼容 shim

阶段 C: 移除 V1 (1.0.0)
  └─ 仅保留 V2 单轨
  └─ _*_core helper 重命名为 public 方法
  └─ 删除所有 pyright: ignore
```

### 合并后目标结构

```
src/lush_sqlalchemyx/base/dal/
├── _common.py          # 共享类型/事件 (不变)
├── _params.py          # SQLAExtra (不变)
├── _async.py           # 合并后的唯一异步 DAL
├── _sync.py            # 合并后的唯一同步 DAL
└── __init__.py         # 导出
```

### 方法签名统一 (合并后)

```python
class AsyncBaseDAL(
    AbstractAsyncBaseDAL[AsyncSession, TableT, DTOModelT, CUModelT, SQLAExtra],
    AbstractAsyncLockDAL[AsyncSession, TableT, CUModelT, SQLAExtra],
    AbstractAsyncAdvancedWriteDAL[AsyncSession, TableT, CUModelT, SQLAExtra],
    AbstractAsyncBatchFieldDAL[AsyncSession, TableT, DTOModelT, SQLAExtra],
    AbstractAsyncRawSQLDAL[AsyncSession, SQLAExtra],
):
    """SQLAlchemy 异步完整 DAL — 单轨实现."""
    _Table: ClassVar[type[TableT]]
    _DTO: ClassVar[type[DTOModelT]]
    _CU: ClassVar[type[CUModelT]]
```

---

## Phase 4: Repository 高层声明式封装

### 动机

当前 DAL 使用需要：
1. 定义 Table/CU/DTO 三个类
2. 定义 DAL class 绑定泛型
3. 获取 session
4. 调用 classmethod

理想开发者体验：

```python
# 声明
class UserRepo(Repository):
    class Meta:
        model = User         # ORM model
        dto = UserDTO
        cu = UserCU

# 使用 (DI 注入 session)
user = await UserRepo.get(1)
users = await UserRepo.list(limit=10)
new_user = await UserRepo.create(UserCU(name="Alice"))
```

### 设计

```python
# lush_dal_protocol/repository.py

class RepositoryMeta:
    """Repository 元数据声明."""
    model: type          # ORM Entity class
    dto: type[BaseDTO]
    cu: type[BaseCU]
    primary_key: str = "id"
    soft_delete: bool = False

class AbstractSyncRepository(ABC, Generic[EntityT, DTOModelT, CUModelT, PrimaryKeyT]):
    """高层声明式 Repository — 隐藏 session 管理细节.

    下游 ORM 适配包提供具体 session 注入方式.
    """

    class Meta(RepositoryMeta): ...

    # ─── 读操作 ───
    @classmethod
    @abstractmethod
    def get(cls, pk: PrimaryKeyT) -> EntityT | None: ...

    @classmethod
    @abstractmethod
    def get_or_raise(cls, pk: PrimaryKeyT) -> EntityT: ...

    @classmethod
    @abstractmethod
    def list(cls, *, skip: int = 0, limit: int = 100) -> list[DTOModelT]: ...

    @classmethod
    @abstractmethod
    def count(cls) -> int: ...

    @classmethod
    @abstractmethod
    def exists(cls, pk: PrimaryKeyT) -> bool: ...

    # ─── 写操作 ───
    @classmethod
    @abstractmethod
    def create(cls, cu: CUModelT) -> EntityT: ...

    @classmethod
    @abstractmethod
    def update(cls, pk: PrimaryKeyT, cu: CUModelT) -> EntityT | None: ...

    @classmethod
    @abstractmethod
    def delete(cls, pk: PrimaryKeyT) -> bool: ...

    # ─── 批量操作 ───
    @classmethod
    @abstractmethod
    def bulk_get(cls, pks: Iterable[PrimaryKeyT]) -> dict[PrimaryKeyT, EntityT]: ...

    @classmethod
    @abstractmethod
    def bulk_update(cls, pks: Iterable[PrimaryKeyT], data: dict[str, Any]) -> int: ...
```

### Repository 与 DAL 的关系

```
Repository (高层, 面向业务开发者)
    │
    ├── 内部委托 → SessionlessDAL (Django/Peewee/Tortoise)
    │
    └── 内部委托 → SessionDAL + SessionFactory (SQLAlchemy)
```

### SQLAlchemy Repository 实现

```python
# lush-sqlalchemyx 中
class SQLAlchemyRepository(AbstractSyncRepository[TableT, DTOModelT, CUModelT, int]):
    """SQLAlchemy 具体 Repository — 通过注入的 session_factory 管理 session."""

    _dal_class: ClassVar[type[SyncBaseDALV2]]
    _session_factory: ClassVar[Callable[[], ContextManager[Session]]]

    @classmethod
    def get(cls, pk: int) -> TableT | None:
        with cls._session_factory() as session:
            return cls._dal_class.get_by_id(session, pk)

    @classmethod
    def create(cls, cu: CUModelT) -> TableT:
        with cls._session_factory() as session:
            entity = cls._dal_class.create(session, cu)
            session.commit()
            return entity
```

---

## Phase 5: 跨 ORM 适配器 (新包)

### 包规划

| 包名 | ORM | 优先级 |
|------|-----|--------|
| `lush-sqlalchemyx` | SQLAlchemy 2.x | 已有 |
| `lush-djangox` | Django ORM | P2 |
| `lush-peeweex` | Peewee 3.x | P3 |
| `lush-tortoisex` | TortoiseORM | P3 |

### 统一 Extra 子类

| ORM | Extra 子类 | 特有字段 |
|-----|-----------|---------|
| SQLAlchemy | `SQLAExtra` | `lock_timeout`, `none_policy`, `version_field` |
| Django | `DjangoExtra` | `using` (db alias), `select_for_update_nowait` |
| Peewee | `PeeweeExtra` | `database` |
| TortoiseORM | `TortoiseExtra` | `connection_name` |

### 统一 Conformance 验证

所有适配器包 **必须** 通过 `lush-dal-protocol` conformance 测试：

```python
# lush-djangox/tests/test_conformance.py
from lush_dal_protocol.testing import SyncFullDALConformanceTests

class TestDjangoDALConformance(SyncFullDALConformanceTests):
    @pytest.fixture
    def dal_class(self): return DjangoUserDAL
    @pytest.fixture
    def session(self): return None  # Django 无 session
    ...
```

---

## 版本发布路线

| 里程碑 | 版本 | 变更 |
|--------|------|------|
| M1 | `lush-dal-protocol 0.2.0` | PrimaryKeyT 泛型 + SessionlessDAL |
| M2 | `lush-sqlalchemyx 0.3.0` | V1 deprecated, V2 推荐 |
| M3 | `lush-dal-protocol 0.3.0` | Repository ABC |
| M4 | `lush-sqlalchemyx 0.4.0` | Repository 实现 + V1 legacy shim |
| M5 | `lush-djangox 0.1.0` | Django adapter + SessionlessDAL 实现 |
| M6 | `lush-sqlalchemyx 1.0.0` | V1 移除, 单轨 |

---

## 设计原则

1. **渐进式 Breaking**: 每个 breaking 变更都有 default 泛型参数 + deprecation 期
2. **Conformance 驱动**: 新 ABC 方法必须有 conformance 测试，先写测试后实现
3. **类型优先**: 所有公开 API 必须在 basedpyright strict 模式下 0 errors/warnings
4. **ORM 无关**: 协议层永远不允许导入具体 ORM 库
5. **一致性**: async/sync 严格镜像, 方法名/语义/返回值类型完全一致
6. **Extra 统一**: 所有 ORM 特有行为通过 `ExtraT` 子类扩展, 不增加方法参数

---

## 附录: 接口映射表 (最终目标态)

### 低层 DAL (显式 session, 适合 SQLAlchemy 和需要精细事务控制的场景)

```python
# 声明
class UserDAL(AsyncBaseDAL[User, UserDTO, UserCU]):
    _Table = User; _DTO = UserDTO; _CU = UserCU

# 使用
async with session_factory() as session:
    user = await UserDAL.get_by_id(session, 1)
    await UserDAL.create(session, UserCU(name="Alice"))
    await session.commit()
```

### 中层 SessionlessDAL (无 session, 适合 Django/Peewee/Tortoise)

```python
# 声明
class UserDAL(DjangoBaseDAL[User, UserDTO, UserCU]):
    _Model = User; _DTO = UserDTO; _CU = UserCU

# 使用
user = UserDAL.get_by_id(1)
UserDAL.create(UserCU(name="Alice"))  # 自动 save
```

### 高层 Repository (声明式, 跨 ORM 统一)

```python
# 声明
class UserRepo(SQLAlchemyRepository):
    class Meta:
        model = User; dto = UserDTO; cu = UserCU

# 使用
user = await UserRepo.get(1)
await UserRepo.create(UserCU(name="Alice"))
```
