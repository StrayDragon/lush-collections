from lush_stdx.enumx import MetaInfoIntEnum, XMetaInfo


class TmpEnum(MetaInfoIntEnum):
    A = (1, XMetaInfo("A"))
    B = (2, XMetaInfo("B"))
