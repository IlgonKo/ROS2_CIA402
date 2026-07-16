import time


class CycleStats:
    def __init__(self):
        self.values = {}
        self.latest = {}
        self.last_tx_time = None

    def add(self, name, seconds):
        self.latest[name] = seconds
        bucket = self.values.setdefault(
            name,
            {
                "count": 0,
                "sum": 0.0,
                "min": None,
                "max": None,
            },
        )
        bucket["count"] += 1
        bucket["sum"] += seconds
        bucket["min"] = seconds if bucket["min"] is None else min(bucket["min"], seconds)
        bucket["max"] = seconds if bucket["max"] is None else max(bucket["max"], seconds)

    def add_tx_time(self, tx_time):
        if self.last_tx_time is not None:
            self.add("tx_gap", tx_time - self.last_tx_time)
        self.last_tx_time = tx_time

    def report_and_reset(self):
        parts = []
        for name in sorted(self.values):
            bucket = self.values[name]
            if bucket["count"] == 0:
                continue
            average = bucket["sum"] / bucket["count"]
            parts.append(
                f"{name}_ms="
                f"min:{bucket['min'] * 1000.0:.3f} "
                f"avg:{average * 1000.0:.3f} "
                f"max:{bucket['max'] * 1000.0:.3f} "
                f"n:{bucket['count']}"
            )

        self.values = {}
        self.latest = {}
        return " | ".join(parts)


def exchange(
    runtime,
    cycles=1,
    cycle_stats=None,
    sleep_after=True,
    dc_cycle_scheduler=None,
):
    for _ in range(cycles):
        exchange_start = time.monotonic()
        if cycle_stats is not None:
            cycle_stats.add_tx_time(exchange_start)
        runtime.prepare_processdata()
        runtime.send_processdata()
        if dc_cycle_scheduler is not None:
            runtime.last_tx_dc_time_ns = (
                dc_cycle_scheduler.estimate_transmit_dc_time_ns(runtime)
            )
        runtime.receive_processdata()
        pdo_done = time.monotonic()
        if sleep_after:
            time.sleep(runtime.cycle_time)
        exchange_done = time.monotonic()
        if cycle_stats is not None:
            cycle_stats.add("pdo_io", pdo_done - exchange_start)
            cycle_stats.add("exchange", exchange_done - exchange_start)


def wait_until_cycle_time(target_time, spin_wait_time):
    spin_wait_time = max(0.0, float(spin_wait_time))
    sleep_until = target_time - spin_wait_time

    now = time.monotonic()
    if now < sleep_until:
        time.sleep(sleep_until - now)

    while time.monotonic() < target_time:
        pass
