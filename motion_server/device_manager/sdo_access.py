class LogicalSdoAccess:
    """Typed SDO access through logical axis/io selectors."""

    def __init__(self, axis_sdo, io_sdo):
        self.axis = axis_sdo
        self.io = io_sdo

    def __getattr__(self, name):
        return getattr(self.axis, name)
