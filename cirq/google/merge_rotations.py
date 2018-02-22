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

from typing import Iterable, List, Tuple

import numpy as np

from cirq import ops
from cirq.circuits import Circuit, InsertStrategy, PointOptimizer
from cirq.extension import Extensions
from cirq.google.decompositions import single_qubit_matrix_to_native_gates
from cirq.google.xmon_gates import XmonGate


class MergeRotations(PointOptimizer):
    """Combines adjacent constant single-qubit rotations."""

    def __init__(self,
                 insert_strategy: InsertStrategy = InsertStrategy.INLINE,
                 tolerance: float = 1e-8,
                 extensions = None):
        self.insert_strategy = insert_strategy
        self.tolerance = tolerance
        self.extensions = extensions or Extensions()

    def optimize_at(self, circuit, index, op):
        if len(op.qubits) != 1:
            return

        indices, gates = self._scan_single_qubit_ops(circuit, index,
                                                     op.qubits[0])
        if not gates or (len(gates) == 1 and isinstance(gates[0], XmonGate)):
            return

        # Replace the gates with a max-2-op XY + Z construction.
        circuit.clear_operations_touching(op.qubits, indices)
        return circuit.insert(index + 1,
                              self._merge_rotations(op.qubits[0], gates),
                              self.insert_strategy)

    def _scan_single_qubit_ops(
            self,
            circuit: Circuit, index: int,
            qubit: ops.QubitId) -> Tuple[List[int], List[ops.Gate]]:
        gates = []
        indices = []
        while index is not None:
            op = circuit.operation_at(qubit, index)
            if len(op.qubits) != 1:
                break
            gate = self.extensions.try_cast(op.gate, ops.KnownMatrixGate)
            if gate is None:
                break
            indices.append(index)
            gates.append(gate)
            index = circuit.next_moment_operating_on([qubit], index + 1)
        return indices, gates

    def _merge_rotations(
            self,
            qubit: ops.QubitId,
            gates: Iterable[ops.KnownMatrixGate]
    ) -> List[ops.Operation]:
        matrix = np.eye(2, dtype=np.complex128)
        for op in gates:
            matrix = np.dot(op.matrix(), matrix)

        gates = single_qubit_matrix_to_native_gates(matrix, self.tolerance)
        return [gate(qubit) for gate in gates]
