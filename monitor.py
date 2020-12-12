import argparse
import gatt
import logging


BUTTON_CODES = {
    b"\xff\x00": "Off",
    b"\xfe\x00": "North",
    b"\xfd\x00": "East",
    b"\xfb\x00": "West",
    b"\xf7\x00": "South",
}
BUTTON_STATUS_SERVICE_UUID = "99c31523-dc4f-41b1-bb04-4e4deb81fadd"

logger = logging.getLogger("monitor")


class TurnTouchDeviceManager(gatt.DeviceManager):
    def device_discovered(self, device):
        super().device_discovered(device)
        logger.info("Discovered %s (%s), connecting...", device.mac_address, device.alias())
        device.connect()

    def make_device(self, mac_address):
        return TurnTouchDevice(mac_address=mac_address, manager=self)


class TurnTouchDevice(gatt.Device):

    battery_status_characteristic = None

    def connect_succeeded(self):
        super().connect_succeeded()
        logger.info("%s: Connected", self.mac_address)

    def connect_failed(self, error):
        super().connect_failed(error)
        logger.info("%s: Connecting failed with error %s", self.mac_address, error)

    def services_resolved(self):
        super().services_resolved()
        button_status_service = next(
            s for s in self.services if s.uuid == BUTTON_STATUS_SERVICE_UUID
        )

        self.button_status_characteristic = next(
            c
            for c in button_status_service.characteristics
            if c.uuid == "99c31525-dc4f-41b1-bb04-4e4deb81fadd"
        )

        self.button_status_characteristic.enable_notifications()

        battery_status_service = next(
            (s for s in self.services if s.uuid.startswith("0000180f")), None
        )

        # Curiously, some Turn Touch remotes lack battery status.
        # (Perhaps an outdated firmware revision?)
        if battery_status_service is not None:
            self.battery_status_characteristic = next(
                (
                    c
                    for c in battery_status_service.characteristics
                    if c.uuid.startswith("00002a19")
                ),
                None,
            )
            if self.battery_status_characteristic is not None:
                self.battery_status_characteristic.read_value()
                self.sched.add_job(
                    self.battery_status_characteristic.read_value,
                    trigger="interval",
                    minutes=1,  # todo: reduce this
                )

    def characteristic_enable_notifications_succeeded(self, characteristic):
        super().characteristic_enable_notifications_succeeded(characteristic)
        logger.info("%s: Characteristic notifications enabled", self.mac_address)

    def characteristic_value_updated(self, characteristic, value):
        super().characteristic_value_updated(characteristic, value)
        if characteristic == self.battery_status_characteristic:
            percentage = int(int.from_bytes(value, byteorder="big") * 100 / 255)
            logger.info("%s: Battery status %s%%", self.mac_address, percentage)
            return
        # if value not in BUTTON_CODES:
        #     logger.warning("%s: Saw value not in button codes", self.mac_address)
        #     return
        # button = BUTTON_CODES[value]
        # logger.info("%s: Button %s", self.mac_address, button)
        buttons = ~(int.from_bytes(value, "little") & 0xFF)
        logger.info("Buttons: %x", buttons)
        bset = set()
        north = buttons & (1 << 0)
        if north:
            bset.add("north")
        east = buttons & (1 << 0)
        if east:
            bset.add("east")
        west = buttons & (1 << 0)
        if west:
            bset.add("west")
        south = buttons & (1 << 0)
        if south:
            bset.add("south")
        if len(bset) == 0:
            logger.info("%s: No buttons")
        else:
            logger.info("%s: Buttons = %s", self.mac_address, ", ".join(bset))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    manager = TurnTouchDeviceManager(adapter_name="hci0")
    manager.start_discovery(
        [
            BUTTON_STATUS_SERVICE_UUID,
            # 1523 is a shorter identifier that TurnTouch Mac also scans for:
            "1523",
        ]
    )
    logger.info("Started discovery, running event loop...")
    manager.run()
