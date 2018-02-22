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

"""Simulator for the Google's Xmon class quantum computers.

The simulator can be used to run all of a Circuit or to step through the
simulation Moment by Moment. The simulator requires that all gates used in
the circuit are either an XmonGate or are CompositeGate which can be
decomposed into XmonGates.

A simple example:
    circuit = Circuit([Moment(X(q1), X(q2)), Moment(CZ(q1, q2)])
    sim = Simulator()
    results = sim.run(circuit)
"""

import functools
import math

from collections import defaultdict
from typing import DefaultDict, Dict, Iterator, Sequence, Tuple, Union

import numpy as np

import cirq
from cirq.circuits import Circuit, ExpandComposite
from cirq.google import xmon_gates, xmon_gate_ext
from cirq.ops import raw_types
from cirq.sim.google.xmon_stepper import Stepper
from cirq.study import Executor
from cirq.study.resolver import ParamResolver


class Options:
    """Options for the Simulator.

    Attributes:
        num_prefix_qubits: Sharding of the wave function is performed over 2
            raised to this value number of qubits.
        min_qubits_before_shard: Sharding will be done only for this number
            of qubits or more. The default is 10.
    """

    def __init__(self, num_shards: int=None, min_qubits_before_shard: int=10):
        """Simulator options constructor.

        Args:
            num_shards: sharding will be done for the greatest value of a
                power of two less than this value. If None, the default will
                be used which is the smallest power of two less than or equal
                to the number of CPUs.
            min_qubits_before_shard: Sharding will be done only for this number
                of qubits or more. The default is 10.
        """
        assert num_shards is None or num_shards > 0, (
            "Num_shards cannot be less than 1.")
        if num_shards is None:
            self.num_prefix_qubits = None
        else:
            self.num_prefix_qubits = int(math.log(num_shards, 2))

        assert min_qubits_before_shard >= 0, (
            'Min_qubit_before_shard must be positive.')
        self.min_qubits_before_shard = min_qubits_before_shard


class Simulator(Executor):
    """Simulator for Xmon class quantum circuits."""

    def run(
            self,
            program: Circuit,
            options: Options = None,
            qubits: Sequence[raw_types.QubitId] = None,
            initial_state: Union[int, np.ndarray] = 0,
            param_resolver: ParamResolver = None,
    ) -> Tuple['TrialContext', 'TrialResult']:
        """Simulates the entire supplied Circuit.

        Args:
            program: The circuit to simulate.
            options: Options configuring the simulation.
            qubits: If specified this list of qubits will be used to define
                a canonical ordering of the qubits. This canonical ordering
                is used to define the wave function.
            initial_state: If an int, the state is set to the computational
                basis state corresponding corresponding to this state. Otherwise
                if this is a np.ndarray it is the full initial state. In this
                case it must be the correct size, be normalized (an L2 norm of
                1), and have a dtype of np.complex64.
            param_resolver: A ParamResolver for determining values of
                ParameterizedValues.

        Returns:
            A tuple (context, result) where context is the TrailContext for
                performing this run and result is the TrailResult containing
                the results of this run.
        """
        param_resolver = param_resolver or ParamResolver({})
        all_step_results = self.moment_steps(program, options or Options(),
                                             qubits,
                                             initial_state, param_resolver)
        context = TrialContext(param_resolver.param_dict)
        final_step_result = functools.reduce(
            StepResult.merge_measurements_with,
            all_step_results)
        return context, TrialResult(final_step_result)

    def moment_steps(
            self,
            program: Circuit,
            options: 'Options' = None,
            qubits: Sequence[raw_types.QubitId] = None,
            initial_state: Union[int, np.ndarray]=0,
            param_resolver: ParamResolver = None) -> Iterator['StepResult']:
        """Returns an iterator of XmonStepResults for each moment simulated.

        Args:
            program: The Circuit to simulate.
            options: Options configuring the simulation.
            qubits: If specified this list of qubits will be used to define
                a canonical ordering of the qubits. This canonical ordering
                is used to define the wave function.
            initial_state: If an int, the state is set to the computational
                basis state corresponding corresponding to this state. Otherwise
                if this is a np.ndarray it is the full initial state. In this
                case it must be the correct size, be normalized (an L2 norm of
                1), and have a dtype of np.complex64.
            param_resolver: A ParamResolver for determining values of
                ParameterizedValues.

        Returns:
            SimulatorIterator that steps through the simulation, simulating
            each moment and returning a StepResult for each moment.
        """
        param_resolver = param_resolver or ParamResolver({})
        return simulator_iterator(program, options or Options(), qubits,
                                  initial_state, param_resolver)


def simulator_iterator(
        circuit: Circuit,
        options: 'Options' = Options(),
        qubits: Sequence[raw_types.QubitId] = None,
        initial_state: Union[int, np.ndarray]=0,
        param_resolver: ParamResolver = ParamResolver({})
) -> Iterator['StepResult']:
    """Iterator over TrialResults from Moments of a Circuit.

    This should rarely be instantiated directly, instead prefer to create an
    Simulator and use methods on that object to get an iterator.

    Args:
        circuit: The circuit to simulate.
        options: Options configuring the simulation.
        qubits: If specified this list of qubits will be used to define
            a canonical ordering of the qubits. This canonical ordering
            is used to define the wave function.
        initial_state: If an int, the state is set to the computational
            basis state corresponding corresponding to this state.
        param_resolver: A ParamResolver for determining values ofs
            ParameterizedValues.

    Yields:
        StepResults from simulating a Moment of the Circuit.
    """
    circuit_qubits = circuit.qubits()
    if qubits is not None:
        assert set(circuit_qubits) <= set(qubits), (
            'Qubits given to simulator were not those in supplied Circuit.')
    else:
        qubits = list(circuit_qubits)
    qubit_map = {q: i for i, q in enumerate(qubits)}
    opt = ExpandComposite()
    circuit_copy = Circuit(circuit.moments)
    opt.optimize_circuit(circuit_copy)
    with Stepper(
        num_qubits=len(qubits),
        num_prefix_qubits=options.num_prefix_qubits,
        initial_state=initial_state,
        min_qubits_before_shard=options.min_qubits_before_shard) as stepper:
        for moment in circuit_copy.moments:
            measurements = defaultdict(list)
            phase_map = {}
            for op in moment.operations:
                gate = xmon_gate_ext.try_cast(op.gate, xmon_gates.XmonGate)
                if isinstance(gate, xmon_gates.ExpZGate):
                    index = qubit_map[op.qubits[0]]
                    phase_map[(index,)] = param_resolver.value_of(
                        gate.half_turns)
                elif isinstance(gate, xmon_gates.Exp11Gate):
                    index0 = qubit_map[op.qubits[0]]
                    index1 = qubit_map[op.qubits[1]]
                    phase_map[(index0, index1)] = (
                        param_resolver.value_of(gate.half_turns))
                elif isinstance(gate, xmon_gates.ExpWGate):
                    index = qubit_map[op.qubits[0]]
                    stepper.simulate_w(
                        index=index,
                        half_turns=param_resolver.value_of(gate.half_turns),
                        axis_half_turns=param_resolver.value_of(
                            gate.axis_half_turns))
                elif isinstance(gate, xmon_gates.XmonMeasurementGate):
                    index = qubit_map[op.qubits[0]]
                    results = stepper.simulate_measurement(index)
                    measurements[gate.key].append(results)
                else:
                    raise TypeError(
                        'Gate %s is not a gate supported by the xmon simulator.'
                        % gate)
            stepper.simulate_phases(phase_map)
            yield StepResult(stepper, qubit_map, measurements)


class TrialContext(cirq.study.TrialContext):
    """The context that generated the result.

    Attributes:
        param_dict: A dictionary produce by the ParamResolver mapping parameter
            keys to actual parameter values that produced this result.
        reptition_id: An id used to identify repetitions within runs for
            a fixed param_dict.
    """

    def __init__(self, param_dict: Dict, repetition_id: int = None):
        self.param_dict = param_dict
        self.repetition_id = repetition_id

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return NotImplemented
        return (self.param_dict == other.param_dict
                and self.repetition_id == other.repetition_id)

    def __neq__(self, other):
        return not self == other


class StepResult:
    """Results of a step of the simulator.

    Attributes:
        qubit_map: A map from the Qubits in the Circuit to the the index
            of this qubit for a canonical ordering. This canonical ordering is
            used to define the state (see the state() method).
        measurements: A dictionary from measurement gate key to measurement
            results. If a key is reused, the measurement values are returned
            in the order they appear in the Circuit being simulated.
    """

    def __init__(
            self,
            stepper: Stepper,
            qubit_map: Dict,
            measurements: DefaultDict):
        self.qubit_map = qubit_map or {}
        self.measurements = measurements or defaultdict(list)
        self._stepper = stepper

    def state(self) -> np.ndarray:
        """Return the state (wave function) at this point in the computation.

        The state is returned in the computational basis with these basis
        states defined by the qubit_map. In particular the value in the
        qubit_map is the index of the qubit, and these are translated into
        binary vectors using little endian.

        Example:
             qubit_map: {Qubit0: 2, Qubit1: 1, Qubit 2: 0}
             Then the returned vector will have indices mapped to qubit basis
             states like the following table
               |   | Qubit0 | Qubit1 | Qubit2 |
               +---+--------+--------+--------+
               | 0 |   0    |   0    |   0    |
               | 1 |   0    |   0    |   1    |
               | 2 |   0    |   1    |   0    |
               | 3 |   0    |   1    |   1    |
               | 4 |   1    |   0    |   0    |
               | 5 |   1    |   0    |   1    |
               | 6 |   1    |   1    |   0    |
               | 7 |   1    |   1    |   1    |
               +---+--------+--------+--------+
        """
        return self._stepper.current_state

    def set_state(self, state: Union[int, np.ndarray]):
        """Updates the state of the simulator to the given new state.

        Args:
            state: If this is an int, then this is the state to reset
            the stepper to, expressed as an integer of the computational basis.
            Integer to bitwise indices is little endian. Otherwise if this is
            a np.ndarray this must be the correct size and have dtype of
            np.complex64.

        Raises:
            ValueError if the state is incorrectly sized or not of the correct
            dtype.
        """
        self._stepper.reset_state(state)

    def merge_measurements_with(self,
        last_result: 'TrialResult') -> 'TrialResult':
        """Merges measurement results of last_result into a new Result.

        The measurement results are merges such that measurements with duplicate
        keys have the results of last_result before those of this objects
        results.

        Args:
            last_result: A Result whose measurement results will be the
                base into which the current Result's measurement results
                are merged.

        Returns:
            A new Result, but with merged measurements.
        """
        new_measurements = defaultdict(list)
        new_measurements.update(last_result.measurements)
        for key, result_list in self.measurements.items():
            new_measurements[key].extend(result_list)
        return StepResult(self._stepper, self.qubit_map, new_measurements)


class TrialResult(cirq.study.TrialResult):
    """Results of a single run of an executor.

    Attributes:
        measurements: A dictionary from measurement gate key to measurement
            results. If a key is reused, the measurement values are returned
            in the order they appear in the Circuit being simulated.
        final_state: The final state (wave function) of the system after
            the trial finishes.
    """

    def __init__(self, final_step_result: StepResult):
        self.measurements = final_step_result.measurements
        # TODO(dabacon): This should be optional, since it can be rather big.
        self.final_state = final_step_result.state()

    def __str__(self):
        def bitstring(vals):
            return ''.join('1' if v else '0' for v in vals)

        keyed_bitstrings = [
            (key, bitstring(val)) for key, val in self.measurements.items()
        ]
        sorted_bitstrings = sorted(keyed_bitstrings, key=lambda e: e[0])
        return '\n'.join('{}: {}'.format(repr(key), val)
                         for key, val in sorted_bitstrings)
