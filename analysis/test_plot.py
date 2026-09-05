import csv
from pathlib import Path
import tempfile
import unittest

from aggregate import aggregate, write_outputs
from plot import plot
from test_aggregate import fixture, LEDGER


class PlotTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        runs,results=fixture()
        self.rows,self.details=aggregate(runs,results,LEDGER)

    def render(self, rows):
        write_outputs(rows,self.details,self.root)
        plot(self.root/'runs.csv',self.root/'chart.png')

    def test_missing_evaluation_remains_in_sidecar_without_mixing_versions(self):
        missing=dict(self.rows[0],run_id='missing',score_version=None,quality_percent=None,evaluation_error='not evaluated')
        self.render(self.rows+[missing])
        with (self.root/'chart.missing-runs.csv').open(encoding='utf-8-sig',newline='') as stream:
            rows=list(csv.DictReader(stream))
        self.assertEqual([r['run_id'] for r in rows],['missing'])
        self.assertEqual(rows[0]['quality_percent'],'')

    def test_reject_mixed_versions_duplicate_runs_and_nonfinite_coordinates(self):
        for extra in (dict(self.rows[0],run_id='other',score_version='v2'),self.rows[0]):
            with self.assertRaises(ValueError):self.render(self.rows+[extra])
        for invalid in ('nan','inf','-1'):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                self.render([dict(self.rows[0],total_tokens=invalid)])

    def test_same_csv_produces_same_png(self):
        self.render(self.rows)
        first=(self.root/'chart.png').read_bytes()
        plot(self.root/'runs.csv',self.root/'chart.png')
        self.assertEqual(first,(self.root/'chart.png').read_bytes())

    def test_different_charts_do_not_overwrite_each_others_missing_table(self):
        missing=dict(self.rows[0],run_id='missing',quality_percent=None)
        self.render(self.rows+[missing])
        original=(self.root/'chart.missing-runs.csv').read_bytes()
        write_outputs(self.rows,self.details,self.root)
        plot(self.root/'runs.csv',self.root/'second.png')
        self.assertEqual(original,(self.root/'chart.missing-runs.csv').read_bytes())


if __name__=='__main__':unittest.main()
