import json
import unittest

from demo import read_saved_examples, score, valid_schema


class ScoringTests(unittest.TestCase):
    def test_recorded_results(self):
        for name, exact, misses in (("base", 11, 10), ("tuned", 27, 6)):
            rows = []
            for r in read_saved_examples(name):
                obj = json.loads(r["raw"])
                rows.append(dict(r, prediction=obj, valid_json=True, valid_schema=valid_schema(obj)))
            result = score(rows)
            self.assertEqual(result["test_size"], 36)
            self.assertAlmostEqual(result["exact_match_rate"], exact / 36)
            self.assertAlmostEqual(result["sev1_miss_rate"], misses / 12)
            self.assertIsNone(result["p95_successful_request_seconds"])

    def test_errors_stay_in_denominator(self):
        expected = dict(category="AUTH_FAILURE", severity="SEV1", team="IDENTITY")
        rows = [dict(expected=expected, prediction=expected, valid_json=True, valid_schema=True),
                dict(expected=expected, prediction={}, valid_json=False, valid_schema=False, error="TimeoutError")]
        result = score(rows)
        self.assertEqual(result["exact_match_rate"], 0.5)
        self.assertEqual(result["sev1_miss_rate"], 0.5)
        self.assertEqual(result["request_errors"], 1)

    def test_schema_rejects_extra_fields_and_wrong_types(self):
        valid = dict(category="AUTH_FAILURE", severity="SEV1", team="IDENTITY")
        self.assertTrue(valid_schema(valid))
        for invalid in ([], None, dict(valid, reason="extra"), dict(valid, severity=1), dict(valid, team="Identity")):
            self.assertFalse(valid_schema(invalid))


if __name__ == "__main__":
    unittest.main()
