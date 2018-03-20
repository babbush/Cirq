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

"""The circuit data structure for the sequenced phase."""

from typing import Any, Callable, Dict, Iterable, Optional, Sequence, Set

from cirq import ops
from cirq.circuits.insert_strategy import InsertStrategy
from cirq.circuits.moment import Moment
from cirq.circuits.text_diagram_drawer import TextDiagramDrawer
from cirq.extension import Extensions
from cirq.ops import QubitId


class Circuit(object):
    """A mutable list of groups of operations to apply to some qubits.

    Attributes:
      moments: A list of the Moments of the circuit.
    """

    def __init__(self, moments: Iterable[Moment] = ()) -> None:
        """Initializes a circuit.

        Args:
            moments: The initial list of moments defining the circuit.
        """
        self.moments = list(moments)

    @staticmethod
    def from_ops(*operations: ops.OP_TREE,
                 strategy: InsertStrategy = InsertStrategy.NEW_THEN_INLINE
                 ) -> 'Circuit':
        """Creates an empty circuit and appends the given operations.

        Args:
            operations: The operations to append to the new circuit.
            strategy: How to append the operations.

        Returns:
            The constructed circuit containing the operations.
        """
        result = Circuit()
        result.append(operations, strategy)
        return result

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return NotImplemented
        return self.moments == other.moments

    def __ne__(self, other):
        return not self == other

    __hash__ = None

    def _first_moment_operating_on(self, qubits: Iterable[ops.QubitId],
                                   indices: Iterable[int]) -> Optional[int]:
        qubits = frozenset(qubits)
        for m in indices:
            if self._has_op_at(m, qubits):
                return m
        return None

    def next_moment_operating_on(self,
                                 qubits: Iterable[ops.QubitId],
                                 start_moment_index: int = 0,
                                 max_distance: int = None) -> Optional[int]:
        """Finds the index of the next moment that touches the given qubits.

        Args:
            qubits: We're looking for operations affecting any of these qubits.
            start_moment_index: The starting point of the search.
            max_distance: The number of moments (starting from the start index
                and moving forward) to check. Defaults to no limit.

        Returns:
            None if there is no matching moment, otherwise the index of the
            earliest matching moment.

        Raises:
          ValueError: negative max_distance.
        """
        if max_distance is None:
            max_distance = float('inf')
        elif max_distance < 0:
            raise ValueError('Negative max_distance: {}'.format(max_distance))

        # Don't bother searching indices past the end of the list.
        max_distance = int(
            min(max_distance, len(self.moments) - start_moment_index))

        return self._first_moment_operating_on(
            qubits,
            range(start_moment_index, start_moment_index + max_distance))

    def prev_moment_operating_on(
            self,
            qubits: Sequence[ops.QubitId],
            end_moment_index: Optional[int] = None,
            max_distance: Optional[int] = None) -> Optional[int]:
        """Finds the index of the next moment that touches the given qubits.

        Args:
            qubits: We're looking for operations affecting any of these qubits.
            end_moment_index: The moment index just after the starting point of
                the reverse search. Defaults to the length of the list of
                moments.
            max_distance: The number of moments (starting just before from the
                end index and moving backward) to check. Defaults to no limit.

        Returns:
            None if there is no matching moment, otherwise the index of the
            latest matching moment.

        Raises:
            ValueError: negative max_distance.
        """
        if max_distance is None:
            max_distance = float('inf')
        elif max_distance < 0:
            raise ValueError('Negative max_distance: {}'.format(max_distance))

        if end_moment_index is None:
            end_moment_index = len(self.moments)

        # Don't bother searching indices past the start of the list.
        max_distance = min(end_moment_index, max_distance)

        # Don't bother searching indices past the end of the list.
        if end_moment_index > len(self.moments):
            d = end_moment_index - len(self.moments)
            end_moment_index -= d
            max_distance -= d
        if max_distance <= 0:
            return None

        return self._first_moment_operating_on(qubits,
                                               (end_moment_index - k - 1
                                                for k in range(max_distance)))

    def operation_at(self,
                     qubit: ops.QubitId,
                     moment_index: int) -> Optional[ops.Operation]:
        """Finds the operation on a qubit within a moment, if any.

        Args:
            qubit: The qubit to check for an operation on.
            moment_index: The index of the moment to check for an operation
                within. Allowed to be beyond the end of the circuit.

        Returns:
            None if there is no operation on the qubit at the given moment, or
            else the operation.
        """
        if not 0 <= moment_index < len(self.moments):
            return None
        for op in self.moments[moment_index].operations:
            if qubit in op.qubits:
                return op
        return None

    def clear_operations_touching(self, qubits: Iterable[ops.QubitId],
                                  moment_indices: Iterable[int]):
        """Clears operations that are touching given qubits at given moments.

        Args:
            qubits: The qubits to check for operations on.
            moment_indices: The indices of moments to check for operations
                within.
        """
        qubits = frozenset(qubits)
        for k in moment_indices:
            if 0 <= k < len(self.moments):
                self.moments[k] = self.moments[k].without_operations_touching(
                    qubits)

    def _pick_or_create_inserted_op_moment_index(
            self, splitter_index: int, op: ops.Operation,
            strategy: InsertStrategy) -> int:
        """Determines and prepares where an insertion will occur.

        Args:
            splitter_index: The index to insert at.
            op: The operation that will be inserted.
            strategy: The insertion strategy.

        Returns:
            The index of the (possibly new) moment where the insertion should
                occur.

        Raises:
            ValueError: Unrecognized append strategy.
        """

        if (strategy is InsertStrategy.NEW or
                strategy is InsertStrategy.NEW_THEN_INLINE):
            self.moments.insert(splitter_index, Moment())
            return splitter_index

        if strategy is InsertStrategy.INLINE:
            if (not self._has_op_at(splitter_index - 1, op.qubits) and
                    0 <= splitter_index - 1 < len(self.moments)):
                return splitter_index - 1

            return self._pick_or_create_inserted_op_moment_index(
                splitter_index, op, InsertStrategy.NEW)

        if strategy is InsertStrategy.EARLIEST:
            if not self._has_op_at(splitter_index, op.qubits):
                p = self.prev_moment_operating_on(op.qubits, splitter_index)
                return p + 1 if p is not None else 0

            return self._pick_or_create_inserted_op_moment_index(
                splitter_index, op, InsertStrategy.INLINE)

        raise ValueError('Unrecognized append strategy: {}'.format(strategy))

    def _has_op_at(self, moment_index, qubits):
        return (0 <= moment_index < len(self.moments) and
                self.moments[moment_index].operates_on(qubits))

    def insert(
            self,
            index: int,
            operation_tree: ops.OP_TREE,
            strategy: InsertStrategy = InsertStrategy.NEW_THEN_INLINE) -> int:
        """Inserts operations into the middle of the circuit.

        Args:
            index: The index to insert all of the operations at.
            operation_tree: An operation or tree of operations.
            strategy: How to pick/create the moment to put operations into.

        Returns:
            The insertion index that will place operations just after the
            operations that were inserted by this method.

        Raises:
            IndexError: Bad insertion index.
            ValueError: Bad insertion strategy.
        """
        if not 0 <= index <= len(self.moments):
            raise IndexError('Insert index out of range: {}'.format(index))

        k = index
        for op in ops.flatten_op_tree(operation_tree):
            p = self._pick_or_create_inserted_op_moment_index(k, op, strategy)
            while p >= len(self.moments):
                self.moments.append(Moment())
            self.moments[p] = self.moments[p].with_operation(op)
            k = max(k, p + 1)
            if strategy is InsertStrategy.NEW_THEN_INLINE:
                strategy = InsertStrategy.INLINE
        return k

    def insert_inline_into_range(self,
                                 operations: ops.OP_TREE,
                                 inline_start: int,
                                 inline_end: int) -> int:
        """Writes operations inline into an area of the circuit.

        Args:
            inline_start: The start of the range (inclusive) to write the
                given operations into.
            inline_end: The end of the range (exclusive) to write the given
                operations into. If there are still operations remaining,
                new moments are created to fit them.
            operations: An operation or tree of operations to insert.

        Returns:
            An insertion index that will place operations after the operations
            that were inserted by this method.

        Raises:
            IndexError: Bad inline_start and/or inline_end.
        """
        if not 0 <= inline_start < inline_end <= len(self.moments):
            raise IndexError('Bad insert indices: [{}, {})'.format(
                inline_start, inline_end))

        operations = list(ops.flatten_op_tree(operations))
        i = inline_start
        op_index = 0
        while op_index < len(operations):
            op = operations[op_index]
            while i < inline_end and self.moments[i].operates_on(op.qubits):
                i += 1
            if i >= inline_end:
                break
            self.moments[i] = self.moments[i].with_operation(op)
            op_index += 1

        if op_index >= len(operations):
            return inline_end

        return self.insert(inline_end, operations[op_index:])

    def append(
            self,
            operation_tree: ops.OP_TREE,
            strategy: InsertStrategy = InsertStrategy.NEW_THEN_INLINE):
        """Appends operations onto the end of the circuit.

        Args:
            operation_tree: An operation or tree of operations.
            strategy: How to pick/create the moment to put operations into.
        """
        self.insert(len(self.moments), operation_tree, strategy)

    def qubits(self) -> Set[QubitId]:
        """Returns the qubits acted upon by Operations in this circuit."""
        return frozenset(q for m in self.moments for q in m.qubits)

    def __repr__(self):
        moment_lines = ('\n    ' + repr(moment) for moment in self.moments)
        return 'Circuit([{}])'.format(','.join(moment_lines))

    def __str__(self):
        return self.to_text_diagram()

    def to_text_diagram(
            self,
            ext: Extensions = Extensions(),
            use_unicode_characters: bool = True,
            transpose: bool = False,
            qubit_order_key: Callable[[ops.QubitId], Any] = None) -> str:
        """Returns text containing a diagram describing the circuit.

        Args:
            ext: For extending gates to implement AsciiDiagrammableGate.
            use_unicode_characters: Activates the use of cleaner-looking
                unicode box-drawing characters for lines.
            transpose: Arranges the wires vertically instead of horizontally.
            qubit_order_key: Transforms each qubit into a key that determines
                how the qubits are ordered in the diagram. Qubits with lower
                keys come first. Defaults to the qubit's __str__, but augmented
                so that lexicographic ordering will respect the order of
                integers within the string (e.g. "name10" will come after
                "name2").

        Returns:
            The ascii diagram.
        """
        if qubit_order_key is None:
            qubit_order_key = _str_lexicographic_respecting_int_order

        qubits = {
            q
            for moment in self.moments for op in moment.operations
            for q in op.qubits
        }
        ordered_qubits = sorted(qubits, key=qubit_order_key)
        qubit_map = {ordered_qubits[i]: i for i in range(len(ordered_qubits))}

        diagram = TextDiagramDrawer()
        for q, i in qubit_map.items():
            diagram.write(0, i, str(q) + ('' if transpose else ': '))

        for moment in [Moment()] * 2 + self.moments + [Moment()]:
            _draw_moment_in_diagram(moment, ext, qubit_map, diagram)

        w = diagram.width()
        for i in qubit_map.values():
            diagram.horizontal_line(i, 0, w)

        if transpose:
            return diagram.transpose().render(
                crossing_char='─' if use_unicode_characters else '-',
                use_unicode_characters=use_unicode_characters)
        return diagram.render(
            crossing_char='┼' if use_unicode_characters else '|',
            horizontal_spacing=3,
            use_unicode_characters=use_unicode_characters)


def _get_operation_text_diagram_symbols(op: ops.Operation, ext: Extensions
                                        ) -> Iterable[str]:
    ascii_gate = ext.try_cast(op.gate, ops.AsciiDiagrammableGate)
    if ascii_gate is not None:
        return ascii_gate.ascii_wire_symbols()
    name = repr(op.gate)
    if len(op.qubits) == 1:
        return [name]
    return ['{}:{}'.format(name, i) for i in range(len(op.qubits))]


def _get_operation_text_diagram_exponent(op: ops.Operation,
                                         ext: Extensions) -> Optional[str]:
    ascii_gate = ext.try_cast(op.gate, ops.AsciiDiagrammableGate)
    if ascii_gate is None:
        return None
    exponent = ascii_gate.ascii_exponent()
    if exponent == 1:
        return None
    if isinstance(exponent, float):
        return repr(exponent)
    s = str(exponent)
    if '+' in s or ' ' in s or '-' in s[1:]:
        return '({})'.format(exponent)
    return s


def _draw_moment_in_diagram(moment: Moment,
                            ext: Extensions,
                            qubit_map: Dict[ops.QubitId, int],
                            out_diagram: TextDiagramDrawer):
    if not moment.operations:
        return []

    x0 = out_diagram.width()
    for op in moment.operations:
        indices = [qubit_map[q] for q in op.qubits]
        y1 = min(indices)
        y2 = max(indices)

        # Find an available column.
        x = x0
        while any(out_diagram.content_present(x, y)
                  for y in range(y1, y2 + 1)):
            x += 1

        # Draw vertical line linking the gate's qubits.
        if y2 > y1:
            out_diagram.vertical_line(x, y1, y2)

        # Print gate qubit labels.
        symbols = _get_operation_text_diagram_symbols(op, ext)
        for s, q in zip(symbols, op.qubits):
            out_diagram.write(x, qubit_map[q], s)

        # Add an exponent to the first label.
        exponent = _get_operation_text_diagram_exponent(op, ext)
        if exponent is not None:
            out_diagram.write(x, y1, '^' + exponent)


def _str_lexicographic_respecting_int_order(value):
    """0-pads digits in a string to hack int order into lexicographic order."""
    s = str(value)

    was_on_digits = False
    last_transition = 0
    output = []

    def dump(k):
        chunk = s[last_transition:k]
        if was_on_digits:
            chunk = chunk.rjust(8, '0')
        output.append(chunk)

    for i in range(len(s)):
        on_digits = s[i].isdigit()
        if was_on_digits != on_digits:
            dump(i)
            was_on_digits = on_digits
            last_transition = i

    dump(len(s))
    return ''.join(output)
