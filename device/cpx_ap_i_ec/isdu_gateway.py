ISDU_ACCESS_BASE_INDEX = 0x2001
ISDU_ACCESS_INDEX_STEP = 0x10


def isdu_access_object_index(module, *, index_stride=ISDU_ACCESS_INDEX_STEP):
    return ISDU_ACCESS_BASE_INDEX + int(module) * int(index_stride)


def resolved_isdu_access_index(index, slot, *, index_stride=ISDU_ACCESS_INDEX_STEP):
    if int(index) != ISDU_ACCESS_BASE_INDEX:
        return int(index)
    return isdu_access_object_index(slot, index_stride=index_stride)
