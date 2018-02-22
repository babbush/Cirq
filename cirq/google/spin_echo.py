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

"""An optimization pass that combines adjacent single-qubit rotations."""
import random
from collections import defaultdict

import numpy as np
from typing import List, Tuple, Optional

from cirq import ops
from cirq.circuits.circuit import Circuit
from cirq.circuits.insert_strategy import InsertStrategy
from cirq.circuits.optimization_pass import OptimizationPass
from cirq.circuits import util
from cirq.extension import Extensions
from cirq.google import ExpWGate, XmonGate, XmonMeasurementGate


class _FlipPhase:
    def __init__(self, flip=False, phase=0):
        self.flip = flip
        self.phase = phase

    @staticmethod
    def random():
        return _FlipPhase(
            flip=random.random() < 0.5,
            phase=random.random() * 2)

    # @staticmethod
    # def from_w(gate: ExpWGate) -> '_FlipPhase':
    #     if gate.half_turns == 0:
    #         return _FlipPhase()
    #     if gate.half_turns != 1:
    #         raise ValueError('Unsupported: {}'.format(gate))
    #     return _FlipPhase(flip=True,
    #                       phase=gate.axis_half_turns * 2)

    def then(self, other: '_FlipPhase') -> '_FlipPhase':
        phase = self.phase
        if other.flip:
            phase *= -1
        phase += other.phase

        return _FlipPhase(flip=self.flip != other.flip, phase=phase)

    def exp_w_after_crossing(self, gate: ExpWGate) -> ExpWGate:
        phase = gate.axis_half_turns
        phase -= self.phase
        if self.flip:
            phase *= -1
        return ExpWGate(
            half_turns=gate.half_turns,
            axis_half_turns=phase)

    def measurement_after_crossing(self, gate: XmonMeasurementGate
                                   ) -> XmonMeasurementGate:
        invert_result = gate.invert_result
        if self.flip:
            invert_result = not invert_result
        return XmonMeasurementGate(key=gate.key,
                                   invert_result=not invert_result)


class SpinEcho(OptimizationPass):
    """Inserts Pauli operations all over the circuit."""

    def __init__(self,
                 insert_strategy: InsertStrategy = InsertStrategy.INLINE,
                 tolerance: float = 1e-8,
                 extensions: Extensions = Extensions()):
        self.insert_strategy = insert_strategy
        self.tolerance = tolerance
        self.extensions = extensions

    def optimize_circuit(self, circuit):
        qubits = circuit.qubits()

        current_correction = {q: _FlipPhase() for q in qubits}

        for i in range(len(circuit.moments)):
            moment = circuit.moments[i]
            available_qubits = set(qubits) - moment.qubits
            for op in moment.operations:
                if isinstance(op, (XmonMeasurementGate, ExpWGate)):
                    available_qubits.add(op.qubits[0])

            next_correction = {q: _FlipPhase() for q in qubits}
            inserted = {q: _FlipPhase.random() for q in qubits}


