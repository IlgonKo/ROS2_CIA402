from enum import Enum

class CiA402State(Enum):

    SWITCH_ON_DISABLED = 0

    READY_TO_SWITCH_ON = 1

    SWITCHED_ON = 2

    OPERATION_ENABLED = 3

    FAULT = 4


class CiA402StateMachine:

    def __init__(self):

        self.state = CiA402State.SWITCH_ON_DISABLED

    def process(self, controlword):
        controlword = int(controlword)

        if controlword & 0x0080:
            if self.state == CiA402State.FAULT:
                self.state = CiA402State.SWITCH_ON_DISABLED
            return

        if (controlword & 0x0087) == 0x0000:
            self.state = CiA402State.SWITCH_ON_DISABLED
            return

        if self.state == CiA402State.SWITCH_ON_DISABLED:

            if (controlword & 0x0087) == 0x0006:

                self.state = \
                    CiA402State.READY_TO_SWITCH_ON

        elif self.state == CiA402State.READY_TO_SWITCH_ON:

            if (controlword & 0x008F) == 0x0007:

                self.state = \
                    CiA402State.SWITCHED_ON
            elif (controlword & 0x0087) == 0x0000:
                self.state = \
                    CiA402State.SWITCH_ON_DISABLED

        elif self.state == CiA402State.SWITCHED_ON:

            if (controlword & 0x008F) == 0x000F:

                self.state = \
                    CiA402State.OPERATION_ENABLED
            elif (controlword & 0x0087) == 0x0006:
                self.state = \
                    CiA402State.READY_TO_SWITCH_ON
            elif (controlword & 0x0087) == 0x0000:
                self.state = \
                    CiA402State.SWITCH_ON_DISABLED

        elif self.state == CiA402State.OPERATION_ENABLED:

            if (controlword & 0x008F) == 0x0007:
                self.state = \
                    CiA402State.SWITCHED_ON
            elif (controlword & 0x0087) == 0x0006:
                self.state = \
                    CiA402State.READY_TO_SWITCH_ON
            elif (controlword & 0x0087) == 0x0000:
                self.state = \
                    CiA402State.SWITCH_ON_DISABLED

        elif self.state == CiA402State.FAULT:

            if controlword & 0x0080:

                self.state = \
                    CiA402State.SWITCH_ON_DISABLED

    def get_statusword(self):

        if self.state == CiA402State.SWITCH_ON_DISABLED:
            return 0x0040

        elif self.state == CiA402State.READY_TO_SWITCH_ON:
            return 0x0021

        elif self.state == CiA402State.SWITCHED_ON:
            return 0x0023

        elif self.state == CiA402State.OPERATION_ENABLED:
            return 0x0027

        return 0x0008
