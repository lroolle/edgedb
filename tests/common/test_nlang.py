#
# This source file is part of the EdgeDB open source project.
#
# Copyright 2008-present MagicStack Inc. and the EdgeDB authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


import unittest

from edgedb.lang.common import nlang


class NLangTests(unittest.TestCase):

    def test_common_nlang_gram_numbers(self):
        w = nlang.WordCombination({nlang.Singular('test'),
                                   nlang.Plural('tests')})
        assert w == 'test'
        assert w.singular == 'test' and w.plural == 'tests'
        with self.assertRaises(AttributeError):
            w.dual
