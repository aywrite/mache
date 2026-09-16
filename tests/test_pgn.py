# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""How a fastchess pgn is split into games, which every tool that reads one
relies on and none of them owns."""

from mache import pgn


def game(white="a", black="b", result="1-0", moves="1. e4 e5 {+0.20/10 0.5s} 2. Nf3"):
    return (
        f'[Event "match"]\n[Round "1"]\n[White "{white}"]\n[Black "{black}"]\n'
        f'[Result "{result}"]\n[TimeControl "10+0.1"]\n[Termination "normal"]\n\n'
        f"{moves} {result}\n\n"
    )


class TestGames:
    def test_every_tag_is_read_from_the_game_it_sits_in(self):
        [(tags, record)] = pgn.games(game())
        assert tags["White"] == "a"
        assert tags["Black"] == "b"
        assert tags["Result"] == "1-0"
        assert tags["TimeControl"] == "10+0.1"
        assert "1. e4 e5" in record

    def test_a_record_with_no_players_is_not_a_game(self):
        header = '[Event "match"]\n[Site "here"]\n\n'
        assert list(pgn.games(header + game())) == [
            (tags, record) for tags, record in pgn.games(game())
        ]

    def test_a_truncated_game_does_not_borrow_the_next_ones_tags(self):
        # an interrupted match can leave a game with its players written and
        # nothing after them, and the next game's result is not its own
        cut = '[Event "match"]\n[Round "1"]\n[White "a"]\n[Black "b"]\n\n'
        read = list(pgn.games(cut + game(result="0-1")))
        assert [tags.get("Result") for tags, _ in read] == [None, "0-1"]

    def test_nothing_before_the_first_event_tag_is_a_game(self):
        assert list(pgn.games('[White "a"]\n[Black "b"]\n\n1. e4 *\n')) == []


class TestReason:
    def test_the_reason_is_the_last_comment(self):
        [(_, record)] = pgn.games(
            game(
                moves="1. e4 {book} e5 {+0.20/10 0.5s} 2. Nf3 {+0.30/10 0.4s, White mates}"
            )
        )
        assert pgn.reason(record) == "+0.30/10 0.4s, White mates"

    def test_a_game_with_no_comment_has_no_reason(self):
        [(_, record)] = pgn.games(game(moves="1. e4 e5 2. Nf3"))
        assert pgn.reason(record) == ""
