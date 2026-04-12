# PN532 I2C Wiring

[← Back to README](../../Readme.md) | [Setup →](setup.md)

Each filament gate gets one PN532 wired directly to that lane's MCU I2C bus. There is no shared bus across lanes — each PN532 talks exclusively to its own EBB42.

```
lane0 EBB42  ←→  PN532 for gate 0
lane1 EBB42  ←→  PN532 for gate 1
lane2 EBB42  ←→  PN532 for gate 2
   ...
```

---

## EBB42 Pin Connections

```
EBB42 / Lane MCU                 PN532 module
────────────────                 ────────────
PB3  (SCL)       ──────────────  SCL
PB4  (SDA)       ──────────────  SDA
3V3              ──────────────  VCC / 3V3
GND              ──────────────  GND
```

> [!WARNING]
> Use 3.3 V for VCC. Many PN532 breakout boards accept 5 V on VCC and use an onboard regulator, but the I2C signal lines must be 3.3 V logic. The EBB42 is a 3.3 V device. Do not apply 5 V to PB3 or PB4.

**Klipper config reference for PB3/PB4:**

```ini
[nfc_gate lane0]
i2c_mcu: lane0
i2c_bus: i2c3_PB3_PB4
```

---

## PN532 Mode Selection

> [!IMPORTANT]
> The PN532 module **must be set to I2C mode** before it is wired. If the mode is wrong the PN532 will not respond on the I2C bus, and symptoms look identical to broken wiring.

The PN532 supports three communication modes selected by two pins: SEL0 and SEL1. Most breakout boards expose these as DIP switches or solder jumpers.

| Mode | SEL0 | SEL1 |
|---|:---:|:---:|
| SPI | 0 | 0 |
| **I2C** | **1** | **0** |
| HSU / UART | 0 | 1 |

Set **SEL0 = 1, SEL1 = 0** for I2C.

Check your specific breakout board's silkscreen. Some boards label these switches `A0`/`A1` or `SSEL0`/`SSEL1`. Some have the switches numbered in reverse order. When in doubt, check the board's datasheet or the PN532 datasheet (NXP UM10232) for the mode selection table.

---

## I2C Address

The PN532 default I2C address is `0x24` (decimal `36`).

On some breakout boards the address is selectable via address pads (often labelled `A0` and `A1`, separate from mode switches):

| A1 | A0 | I2C address |
|:---:|:---:|:---:|
| 0 | 0 | `0x24` — default |
| 0 | 1 | `0x25` |
| 1 | 0 | `0x26` |
| 1 | 1 | `0x27` |

For this design, **each lane has its own dedicated I2C bus**, so every PN532 can stay at the default address `0x24`. Address selection is only needed if you are putting multiple PN532s on a single shared bus — which is not required with per-lane EBB42 boards.

The address is set in `nfc_vars.cfg`:

```ini
[nfc_gate]
i2c_address: 36
```

Decimal `36` equals `0x24`. Change this only if your board's address pads are set differently.

---

## Sharing the Bus with a BME280

The EBB42 typically carries a BME280 temperature/humidity sensor on the same PB3/PB4 I2C bus. The PN532 and BME280 can coexist because their I2C addresses are different:

| Device | Default address |
|---|---|
| PN532 | `0x24` (decimal 36) |
| BME280 | `0x76` (decimal 118) |

There is no address conflict. Both devices can sit on the same `i2c3_PB3_PB4` bus.

> [!NOTE]
> If your BME280 was working before adding the PN532 and fails after, the problem is almost always: wrong PN532 mode (SPI/UART mode holds the bus), excessive pullups, or a partially shorted SDA/SCL wire from the PN532 wiring. See [Troubleshooting](troubleshooting.md#bme280-fails-after-pn532-is-added).

---

## Pullups

I2C requires pull-up resistors on SDA and SCL.

Most PN532 breakout boards include onboard 10 kΩ pull-ups. The EBB42 also has pull-ups for its I2C bus. This combination typically works fine.

**What to watch for:**

- Too many parallel pull-ups (multiple boards each with their own) drives the effective resistance down, which can cause marginal signalling, especially at 400 kHz.
- If the bus becomes unreliable after adding the PN532, measure or calculate the parallel resistance: three 10 kΩ resistors in parallel → ~3.3 kΩ. That is fine. Six in parallel → ~1.7 kΩ. That may be too strong.

If pull-ups are suspected: remove or disable the PN532 board's onboard resistors (solder jumpers on some boards) and rely on the MCU's pull-ups.

---

## Wire Length and Quality

Keep I2C wires short during initial bring-up — under 20 cm if possible. Longer cables add capacitance that rounds off signal edges, making marginal timing worse.

Once the system is confirmed working, longer cables (up to ~50 cm) are usually fine at 400 kHz. If you see intermittent failures at longer lengths, reduce `i2c_speed` in `pn532_i2C.cfg` to 100000.

---

## Bring-Up Order

Follow this sequence to avoid chasing phantom failures:

1. Confirm Happy Hare can see the lane MCU on its own (no PN532 connected yet).
2. If a BME280 is fitted, confirm it reads correctly.
3. Set the PN532 DIP switches / jumpers to I2C mode.
4. Connect VCC and GND to the PN532.
5. Connect SDA and SCL.
6. Restart Klipper.
7. Run `NFC_GATE NAME=lane0 INIT=1`.
8. If INIT succeeds, run `NFC_GATE NAME=lane0 SCAN=1` with a tag nearby.

If the BME280 fails only after the PN532 is connected and powered, the problem is physical — mode selection, swapped SDA/SCL, or pull-up interaction. It is not a Spoolman or Happy Hare problem.
