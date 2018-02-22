# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest

from cirq import ops
from cirq.circuits import Circuit, from_ascii, Moment
from cirq.google import XmonQubit


def from_ascii_xmon(text):
    return from_ascii(text, XmonQubit.try_parse_from_ascii)


def test_from_ascii_empty():
    assert from_ascii_xmon('') == Circuit()

    assert from_ascii_xmon('(0, 0): ------') == Circuit()

    assert from_ascii_xmon("""
(0, 0): ------
    """) == Circuit()

    assert from_ascii_xmon("""
(0, 0): ------

(0, 1): ------
    """) == Circuit()


def test_from_ascii_single_qubit_ops():
    q00 = XmonQubit(0, 0)
    q12 = XmonQubit(1, 2)
    assert from_ascii_xmon('(0, 0): --X--') == Circuit([Moment([ops.X(q00)])])

    assert from_ascii_xmon('(0, 0): --X^0.5--') == Circuit(
        [Moment([ops.X(q00)**0.5])])

    assert from_ascii_xmon('(1, 2): --Z--') == Circuit([Moment([ops.Z(q12)])])

    assert from_ascii_xmon("""
(0, 0): --Z--
(1, 2): --X--
        """) == Circuit([Moment([ops.Z(q00),
                                 ops.X(q12)])])


def test_from_ascii_two_qubit_ops():
    q00 = XmonQubit(0, 0)
    q10 = XmonQubit(1, 0)

    assert from_ascii_xmon("""
(0, 0): --.--
(1, 0): --X--
        """) == Circuit([Moment([ops.CNOT(q00, q10)])])

    assert from_ascii_xmon("""
(0, 0): --x--
(1, 0): --.--
        """) == Circuit([Moment([ops.CNOT(q10, q00)])])

    assert from_ascii_xmon("""
(0, 0): --Z--
          |
(1, 0): --X--
        """) == Circuit([Moment([ops.CNOT(q00, q10)])])

    assert from_ascii_xmon("""
(0, 0): --Z--
          |
(2, 0): --|--
(1, 0): --Z--
        """) == Circuit([Moment([ops.CZ(q00, q10)])])

    assert from_ascii_xmon("""
(0, 0): --Z-----
          |^0.5
(1, 0): --Z-----
        """) == Circuit([Moment([ops.CZ(q00, q10)**0.5])])

    assert from_ascii_xmon("""
(0, 0): --@-----
          |^0.5
(2, 0): --+-----
          |^0.5
(1, 0): --Z^0.5-
        """) == Circuit([Moment([ops.CZ(q00, q10)**0.125])])


def test_from_ascii_teleportation_from_diagram():
    ali = XmonQubit(0, 0)
    bob = XmonQubit(0, 1)
    msg = XmonQubit(1, 0)
    tmp = XmonQubit(1, 1)

    assert from_ascii_xmon("""
(1, 0): ------X^0.5--@-H-M----@---
                     |        |
(0, 0): --H-@--------X---M-@--|---
            |              |  |
(0, 1): ----X--------------X--|-Z-
(1, 1): ----------------------X-@-
        """) == Circuit([
            Moment([ops.H(ali)]),
            Moment([ops.CNOT(ali, bob)]),
            Moment([ops.X(msg)**0.5]),
            Moment([ops.CNOT(msg, ali)]),
            Moment([ops.H(msg)]),
            Moment(
                [ops.MeasurementGate()(msg),
                 ops.MeasurementGate()(ali)]),
            Moment([ops.CNOT(ali, bob)]),
            Moment([ops.CNOT(msg, tmp)]),
            Moment([ops.CZ(bob, tmp)]),
        ])


def test_from_ascii_fail_on_duplicate_qubit():
    with pytest.raises(ValueError):
        _ = from_ascii_xmon("""
(0, 0): -X---
(0, 0): ---X-
        """)


def test_fail_on_double_colon():
    with pytest.raises(ValueError):
        _ = from_ascii_xmon("""
(0, 0): -X-:-
        """)


def test_fail_on_unknown_operation():
    with pytest.raises(ValueError):
        _ = from_ascii_xmon("""
(0, 0): --unknown--
        """)


def test_fail_on_adjacent_operations():
    with pytest.raises(ValueError):
        _ = from_ascii_xmon("""
(0, 0): --XY--
        """)
