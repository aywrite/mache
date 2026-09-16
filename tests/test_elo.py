# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""The logistic model both estimators read a score with."""

import pytest

from mache import elo


class TestModel:
    def test_an_even_match_scores_a_half(self):
        assert elo.expected(0) == 0.5

    def test_the_stronger_side_scores_more(self):
        assert elo.expected(100) > 0.5 > elo.expected(-100)
        assert elo.expected(100) + elo.expected(-100) == pytest.approx(1.0)

    def test_the_difference_is_the_model_the_other_way_round(self):
        for figure in (-350.0, -1.0, 0.0, 57.5, 400.0):
            assert elo.difference(elo.expected(figure)) == pytest.approx(figure)

    def test_a_score_of_a_half_is_no_difference(self):
        assert elo.difference(0.5) == 0.0

    def test_four_hundred_elo_is_ten_to_one(self):
        # the scale's own definition: 400 elo is odds of ten to one
        assert elo.expected(400) == pytest.approx(10 / 11)
