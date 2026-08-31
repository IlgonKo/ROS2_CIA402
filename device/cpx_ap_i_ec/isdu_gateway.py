ISDU_ACCESS_BASE_INDEX = 0x2001
ISDU_ACCESS_INDEX_STEP = 0x10


def isdu_access_object_index(module):
    return ISDU_ACCESS_BASE_INDEX + (int(module) - 1) * ISDU_ACCESS_INDEX_STEP


def resolved_isdu_access_index(index, slot):
    if int(index) != ISDU_ACCESS_BASE_INDEX:
        return int(index)
    return isdu_access_object_index(slot)
