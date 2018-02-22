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

import random

import cirq
import cirq.google

def main():

    def generate_supremacy_circuit(device, cz_depth):

        circuit = cirq.Circuit()

        i = 0
        while cz_depth > 0:
            cz_layer = make_cz_layer(device, i)
            if cz_layer:
                circuit.append(make_random_single_qubit_op_layer(device))
                circuit.append(make_cz_layer(device, i))
                cz_depth -= 1
            i += 1

        circuit.append(make_random_single_qubit_op_layer(device))
        circuit.append(cirq.google.XmonMeasurementGate().on(q)
                       for q in device.qubits)

        return circuit

    def make_random_single_qubit_op_layer(device):
        vals = [random.randint(0, 7) / 4.0 for _ in device.qubits]
        phases = [random.randint(0, 7) / 4.0 for _ in device.qubits]
        return [
            cirq.google.ExpWGate(half_turns=angle, axis_half_turns=axis).on(q)
            for angle, axis, q in zip(vals, phases, device.qubits)
            if angle
        ]


    def make_cz_layer(device, layer_index):
        """
        Each layer index corresponds to a shift/transpose of this CZ pattern:

            ●───●   ●   ●   ●───●   ●   ● . . .

            ●   ●   ●───●   ●   ●   ●───● . . .

            ●───●   ●   ●   ●───●   ●   ● . . .

            ●   ●   ●───●   ●   ●   ●───● . . .

            ●───●   ●   ●   ●───●   ●   ● . . .

            ●   ●   ●───●   ●   ●   ●───● . . .
            .   .   .   .   .   .   .   . .
            .   .   .   .   .   .   .   .   .
            .   .   .   .   .   .   .   .     .

        Labelled edges, showing the exact index-to-CZs mapping (mod 8):

             ●─0─●─2─●─4─●─6─●─0─. . .
            1│  5│  1│  5│  1│
             ●─4─●─6─●─0─●─2─●─4─. . .
            3│  7│  3│  7│  3│
             ●─0─●─2─●─4─●─6─●─0─. . .
            5│  1│  5│  1│  5│
             ●─4─●─6─●─0─●─2─●─4─. . .
            7│  3│  7│  3│  7│
             ●─0─●─2─●─4─●─6─●─0─. . .
            1│  5│  1│  5│  1│
             .   .   .   .   .   .
             .   .   .   .   .     .
             .   .   .   .   .       .

        Note that, for small devices, some layers will be empty because the layer
        only contains edges not present on the device.
        """

        dir_x = layer_index % 2
        dir_y = 1 - dir_x
        shift = (layer_index >> 1) % 4

        for q in device.qubits:
            q2 = cirq.google.XmonQubit(q.x + dir_x, q.y + dir_y)
            if q2 not in device.qubits:
                continue  # This edge isn't on the device.
            if (q.x * (2 - dir_x) + q.y * (2 - dir_y)) % 4 != shift:
                continue  # No CZ along this edge for this layer.

            yield cirq.google.Exp11Gate().on(q, q2)
