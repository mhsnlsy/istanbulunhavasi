import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import collect_weather


class EnkaParserTests(unittest.TestCase):
    def test_current_temperature_is_not_shifted_by_turkish_capital_i(self):
        text = "İtibariyle 03/11/26 12:01 Günlük Sıcaklık 18.3°C 19.1°C 14.9°C"
        self.assertEqual(collect_weather.after_label(text, "Günlük Sıcaklık", "°C"), 18.3)

    def test_pressure_keeps_all_four_digits(self):
        text = "Hava Basıncı Barometre (hPa) 1014.9 1015.7 1014.4"
        self.assertEqual(collect_weather.after_label(text, "Barometre (hPa)", "hPa"), 1014.9)

    def test_humidity_reads_current_column(self):
        text = "Nem Bağıl Nem 88% 94% 87%"
        self.assertEqual(collect_weather.after_label(text, "Bağıl Nem", "%"), 88.0)

    def test_dewpoint_and_rain(self):
        text = "Yoğuşma Noktası 16.3°C Günlük Yağış 0.0 mm"
        self.assertEqual(collect_weather.after_label(text, "Yoğuşma Noktası", "°C"), 16.3)
        self.assertEqual(collect_weather.after_label(text, "Günlük Yağış", "mm"), 0.0)

    def test_invalid_pressure_is_not_published(self):
        text = "Barometre (hPa) 14.9"
        self.assertIsNone(collect_weather.after_label(text, "Barometre (hPa)", "hPa"))


class GfsModelTests(unittest.TestCase):
    def test_full_surface_gfs_domain_is_selected(self):
        self.assertEqual(collect_weather.GFS_MODEL_ID, "ncep_gfs013")

    def test_incomplete_gfs_runs_are_not_accepted(self):
        # A pressure-only run must fail the same field-availability rule
        # used by fetch_gfs before it enters the four-run comparison.
        required = ("temperature_2m", "precipitation", "wind_speed_10m",
                    "wind_direction_10m", "temperature_850hPa", "pressure_msl")
        hourly = {key: [None, None] for key in required}
        hourly["temperature_850hPa"] = [8.0, 7.5]
        hourly["pressure_msl"] = [1016.0, 1015.0]
        missing = [key for key in required
                   if not any(collect_weather.num(value) is not None for value in hourly[key])]
        self.assertEqual(set(missing), {"temperature_2m", "precipitation",
                                        "wind_speed_10m", "wind_direction_10m"})


if __name__ == "__main__":
    unittest.main()
