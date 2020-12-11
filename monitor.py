import argparse
import gatt
import logging


BUTTON_STATUS_SERVICE_UUID = '99c31523-dc4f-41b1-bb04-4e4deb81fadd'


logger = logging.getLogger('monitor')


class TurnTouchDeviceManager(gatt.DeviceManager):
    def device_discovered(self, device):
        super().device_discovered(device)
        logger.info(
            "Discovered %s (%s)",
            device.mac_address, device.alias()
        )

    def make_device(self, mac_address):
        return TurnTouchDevice(mac_address=mac_address, manager=self)


class TurnTouchDevice(gatt.Device):

    button_codes = {
        b'\xff\x00': 'Off',
        b'\xfe\x00': 'North Press',
        b'\xef\x00': 'North Double',
        b'\xfe\xff': 'North Hold',
        b'\xfd\x00': 'East Press',
        b'\xdf\x00': 'East Double',
        b'\xfd\xff': 'East Hold',
        b'\xfb\x00': 'West Press',
        b'\xbf\x00': 'West Double',
        b'\xfb\xff': 'West Hold',
        b'\xf7\x00': 'South Press',
        b'\x7f\x00': 'South Double',
        b'\xf7\xff': 'South Hold'
    }

    battery_status_characteristic = None
    battery_notifications_sent = []

    def connect_succeeded(self):
        super().connect_succeeded()
        logger.info("%s: Connected", self.mac_address)

    def connect_failed(self, error):
        super().connect_failed(error)
        logger.info(
            "%s: Connecting failed with error %s",
            self.mac_address, error
        )

    def services_resolved(self):
        super().services_resolved()
        button_status_service = next(
            s for s in self.services
            if s.uuid == BUTTON_STATUS_SERVICE_UUID
        )

        self.button_status_characteristic = next(
            c for c in button_status_service.characteristics
            if c.uuid == '99c31525-dc4f-41b1-bb04-4e4deb81fadd'
        )

        self.button_status_characteristic.enable_notifications()

        battery_status_service = next(
            s for s in self.services
            if s.uuid.startswith('0000180f'),
            None
        )

        # Curiously, some Turn Touch remotes lack battery status.
        # (Perhaps an outdated firmware revision?)
        if battery_status_service is not None:
            self.battery_status_characteristic = next(
                c for c in battery_status_service.characteristics
                if c.uuid.startswith('00002a19'),
                None
            )
            if self.battery_status_characteristic is not None:
                self.battery_status_characteristic.read_value()
                self.sched.add_job(
                    self.battery_status_characteristic.read_value,
                    trigger='interval',
                    minutes=1  # todo: reduce this
                )

    def characteristic_enable_notifications_succeeded(self, characteristic):
        super().characteristic_enable_notifications_succeeded(characteristic)
        logger.info(
            "%s: Characteristic notifications enabled",
            self.mac_address
        )

    def characteristic_value_updated(self, characteristic, value):
        super().characteristic_value_updated(characteristic, value)
        if characteristic == self.battery_status_characteristic:
            percentage = int(int.from_bytes(
                value, byteorder='big') * 100 / 255)
            logger.info(
                "%s: Battery status %s%%",
                self.mac_address, percentage
            )
            return
        if value == b'\xff\x00':  # off
            return
        direction, action = self.button_codes[value].split(' ')
        if action == 'Press':
            self.perform(direction, action)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    args = parser.parse_args()

    logging.basicConfig(
        format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
        datefmt='%H:%M:%S',
        level=logging.INFO)

    manager = TurnTouchDeviceManager(adapter_name='hci0')
    manager.start_discovery([
        BUTTON_STATUS_SERVICE_UUID,
        # 1523 is a shorter identifier that TurnTouch Mac also scans for:
        "1523",
    ])
    manager.run()
