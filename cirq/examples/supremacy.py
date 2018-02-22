import random

import cirq
import cirq.google


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
    Layer index (mod 8) to edge position chart:

     ●─1─●─3─●─5─●─7─●─1─. . .
    2│  6│  2│  6│  2│
     ●─5─●─7─●─1─●─3─●─5─. . .
    4│  8│  4│  8│  4│
     ●─1─●─3─●─5─●─7─●─1─. . .
    6│  2│  6│  2│  6│
     ●─5─●─7─●─1─●─3─●─5─. . .
    8│  4│  8│  4│  8│
     ●─1─●─3─●─5─●─7─●─1─. . .
    2│  6│  2│  6│  2│
     .   .   .   .   .   .
     .   .   .   .   .     .
     .   .   .   .   .       .
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
