# lush-dalx

ORM 无关的数据访问层 (DAL) 协议抽象包。

仅包含纯 Protocol / 接口声明，不依赖任何具体 ORM。
下游适配包（如 `lush-sqlalchemyx`）负责实现这些协议。
