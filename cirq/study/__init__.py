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

"""Types and methods for running studies (repeated trials)."""

from cirq.study.parameterized_value import (
    ParameterizedValue,
)
from cirq.study.resolver import (
    ParamResolver,
)
from cirq.study.study import (
    Executor,
    ExecutorStudy,
    StudyInterface,
    TrialContext,
    TrialContextMeta,
    TrialResult,
    TrialResultMeta,
)
