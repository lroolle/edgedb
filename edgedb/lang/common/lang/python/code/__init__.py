##
# Copyright (c) 2012 Sprymix Inc.
# All rights reserved.
#
# See LICENSE for details.
##


"""This package provides utilities to allow creation and modification of
python code objects on the opcode level"""


import dis
import types

from semantix.utils.datastructures import OrderedSet
from . import opcodes


OP_SETUP_EXCEPT     = opcodes.SETUP_EXCEPT
OP_SETUP_FINALLY    = opcodes.SETUP_FINALLY
OP_JUMP_ABSOLUTE    = opcodes.JUMP_ABSOLUTE
OP_JUMP_FORWARD     = opcodes.JUMP_FORWARD
OP_FOR_ITER         = opcodes.FOR_ITER
OP_EXTENDED_ARG     = opcodes.EXTENDED_ARG
OP_YIELD_VALUE      = opcodes.YIELD_VALUE
OP_EXTENDED_ARG     = opcodes.EXTENDED_ARG

#: If we have any of the following opcodes is in the code object -
#: its CO_OPTIMIZED flag should be off.
#:
_OPTIMIZE_NEG_SET   = {opcodes.LOAD_NAME, opcodes.STORE_NAME, opcodes.DELETE_NAME}


# Some important flags from 'Python/code.h'.
# Only actual and in-use flags are listed here.
#
CO_OPTIMIZED        = 0x0001
CO_NEWLOCALS        = 0x0002
CO_VARARGS          = 0x0004
CO_VARKEYWORDS      = 0x0008
CO_GENERATOR        = 0x0020
CO_NOFREE           = 0x0040


class Code:
    '''A more convenient to modify representation of python code block.

    To simplify working with opcodes and their arguments, we treat an opcode as
    an object (see ``utils.lang.python.code.opcodes`` module for details), which
    encapsulartes its argument and its actual meaning. For instance, the ``LOAD_FAST``
    opcode has an attribute 'local', which contains the name of a local variable.

    As a usage example, let's say we need to transform a regular python function
    to a generator.

    .. code-block:: python

        def pow2(a):
            return a ** 2

        code = Code.from_code(pow2.__code__)

        del code.ops[-1] # Delete the RETURN_VALUE opcode

        # And add opcodes necessary to define and correctly
        # terminate a generator function:
        #
        code.ops.extend((opcodes.YIELD_VALUE(),
                         opcodes.POP_TOP(),
                         opcodes.LOAD_CONST(const=None),
                         opcodes.RETURN_VALUE()))

        pow2.__code__ = code.to_code()

    .. code-block:: pycon

        >>> pow2(10)
        <generator object...

        >>> list(pow2(10))
        [100]
    '''

    __slots__ = 'ops', 'vararg', 'varkwarg', 'newlocals', 'filename', \
                'firstlineno', 'name', 'args', 'kwonlyargs', 'varnames', \
                'freevars', 'cellvars', 'docstring'

    def __init__(self, ops=None, *, vararg=None, varkwarg=None, newlocals=False,
                 filename='<string>', firstlineno=0, name='<code>',
                 args=None, kwonlyargs=None, varnames=None,
                 freevars=None, cellvars=None,
                 docstring=None):

        '''
        :param ops: List of ``opcode.OpCode`` instances.

        :param bool newlocals: Should a new local namespace be created.  Should be
                               set to ``True`` for functions' code objects.

        :param string filename: Filename of the code object.
        :param int firstlineno: First line number of first instruction of the code object.
        :param string name: Name of the code object.  I.e. for functions it contains the
                            function name.

        :param string vararg: Name of ``*args`` argument. I.e. for ``*arg``
                              it is going to be ``'arg'``. Only for a code object
                              of a function.

        :param string varkwarg: Name of ``**kwargs`` argument. I.e. for ``**kwarg``
                                it is going to be ``'kwarg'``. Only for a code object
                                of a function.

        :param tuple(string) args: Names of function's arguments. Only for a code object
                                   of a function.

        :param tuple(string) kwonlyargs: Names of function's arguments. Only for a code object
                                         of a function.

        :param tuple(string) varnames: Names of local variables of the code object.
                                       **Different** from the standard 'co_varnames' as does
                                       not describe function arguments.

        :param tuple(string) freevars: Names of free variables (the ones that are from outer
                                       scopes)

        :param tuple(string) cellvars: Names of cell variables (the ones that are used from
                                       the inner scopes)

        :param str docstring: Documentation string for the code object.

        .. note:: We don't have a ``co_names`` property.  It is computed dynamically, on the
                  assumption, that ``co_names`` are the variable names that are not in
                  ``co_varnames``, ``co_freevars``, ``co_cellvars``.

                  Same for ``co_consts`` - it is computed dynamically too, extracting values
                  of constants from opcodes.
        '''

        if ops is None:
            self.ops = []
        else:
            self.ops = ops

        self.vararg = vararg
        self.varkwarg = varkwarg
        self.newlocals = newlocals
        self.filename = filename
        self.firstlineno = firstlineno
        self.name = name
        self.args = args
        self.kwonlyargs = kwonlyargs
        self.varnames = varnames
        self.freevars = freevars
        self.cellvars = cellvars
        self.docstring = docstring

    def _calc_stack_size(self):
        # The algorithm is almost directly translated to python from c,
        # from 'Python/compile.c', function 'stackdepth()'

        seen = set()
        startdepths = {}
        ops = self.ops
        ops_len = len(ops)

        def walk(idx, depth, maxdepth):
            if idx >= ops_len:
                return maxdepth

            op = ops[idx]

            if op in seen or startdepths.get(op, -100000) >= depth:
                return maxdepth

            seen.add(op)
            startdepths[op] = depth
            try:
                depth += op.stack_effect
                if depth > maxdepth:
                    maxdepth = depth
                assert depth >= 0

                jump = None
                if op.has_jrel:
                    jump = op.jrel
                elif op.has_jabs:
                    jump = op.jabs

                if jump is not None:
                    op_cls = op.__class__
                    target_depth = depth

                    if op_cls in (OP_SETUP_EXCEPT, OP_SETUP_FINALLY):
                        target_depth += 3
                        if target_depth > maxdepth:
                            maxdepth = target_depth
                    elif op_cls is OP_FOR_ITER:
                        target_depth -= 2

                    maxdepth = walk(ops.index(jump), target_depth, maxdepth)

                    if op_cls in (OP_JUMP_ABSOLUTE, OP_JUMP_FORWARD):
                        return maxdepth

                return walk(idx + 1, depth, maxdepth)
            finally:
                seen.discard(op)

        return walk(0, 0, 0)

    def _calc_flags(self):
        ops_set = {op.__class__ for op in self.ops}

        flags = 0

        if not len(_OPTIMIZE_NEG_SET & ops_set):
            flags |= CO_OPTIMIZED

        if OP_YIELD_VALUE in ops_set:
            flags |= CO_GENERATOR

        if not len(opcodes.FREE_OPS & ops_set):
            flags |= CO_NOFREE

        if self.vararg:
            flags |= CO_VARARGS

        if self.varkwarg:
            flags |= CO_VARKEYWORDS

        if self.newlocals:
            flags |= CO_NEWLOCALS

        return flags

    def to_code(self):
        '''Compiles the code object to the standard python's code object.'''

        # Fill 'co_varnames' with function arguments names first.  It will be
        # extended with the names of local variables in later stages.
        # Initialize 'co_argcount', since we know everything we need about
        # arguments at this point.
        #
        co_varnames = OrderedSet()
        if self.args:
            co_varnames.extend(self.args)
        co_argcount = len(co_varnames)
        if self.kwonlyargs:
            co_varnames.extend(self.kwonlyargs)
        co_kwonlyargcount = len(self.kwonlyargs)
        if self.vararg:
            co_varnames.append(self.vararg)
        if self.varkwarg:
            co_varnames.append(self.varkwarg)
        if self.varnames:
            co_varnames.extend(self.varnames)

        co_names = OrderedSet()
        co_cellvars = OrderedSet()
        co_freevars = OrderedSet()
        co_consts = OrderedSet([self.docstring])

        # Stage 1.
        # Go through all opcodes and fill up 'co_varnames', 'co_names',
        # 'co_freevars', 'co_cellvars' and 'co_consts'
        #
        # Later, in Stage 2 we'll need the exact indexes of values in
        # those lists.
        #
        for op in self.ops:
            if op.has_local:
                co_varnames.add(op.local)
            elif op.has_name:
                co_names.add(op.name)
            elif op.has_free:
                try:
                    cell = op.cell
                except AttributeError:
                    co_freevars.add(op.free)
                else:
                    co_cellvars.add(cell)
            elif op.has_const:
                co_consts.add(op.const)

        # Stage 2.
        # Now we start to write opcodes to the 'code' bytearray.
        # Since we don't know the final addresses of all commands, we can't yet
        # resolve jumps, so we memorize positions where to insert jump addresses
        # in 'jumps' list, write 0s for now, and in Stage 3 we will write the
        # already known addresses in place of those 0s.
        #
        # At this stage we also calculate 'co_lnotab'.
        #
        code = bytearray()

        # Addresses of all opcodes to resolve jumps later
        addrs = {}
        # Where to write jump addresses later
        jumps = []

        # A marker.
        no_arg = object()

        len_co_cellvars = len(co_cellvars)
        lnotab = bytearray()
        lastlineno = self.firstlineno
        lastlinepos = 0

        for op in self.ops:
            addr = len(code)
            code.append(op.code)
            addrs[op] = addr

            # Update 'co_lnotab' if we have a new line
            try:
                line = op.lineno
            except AttributeError:
                pass
            else:
                inc_line = line - lastlineno
                inc_pos = addr - lastlinepos
                lastlineno = line
                lastlinepos = addr

                if inc_line == inc_pos == 0:
                    lnotab.extend((0, 0))
                else:
                    # See 'Objects/lnotab_notes.txt' (in python source code)
                    # for details
                    #
                    while inc_pos > 255:
                        lnotab.extend((255, 0))
                        inc_pos -= 255
                    while inc_line > 255:
                        lnotab.extend((inc_pos, 255))
                        inc_pos = 0
                        inc_line -= 255
                    if inc_pos != 0  or inc_line != 0:
                        lnotab.extend((inc_pos, inc_line))

            arg = no_arg

            if op.has_local:
                arg = co_varnames.index(op.local)
            elif op.has_name:
                arg = co_names.index(op.name)
            elif op.has_free:
                try:
                    cell = op.cell
                except AttributeError:
                    # We adjust position with 'len_co_cellvars', as the same opcode
                    # can sometimes have its 'free' argument be set to either a 'cell'
                    # or 'free' variable
                    #
                    arg = co_freevars.index(op.free) + len_co_cellvars
                else:
                    arg = co_cellvars.index(cell)
            elif op.has_const:
                arg = co_consts.index(op.const)
            elif op.has_jrel:
                # Don't know the address yet. Will resolve that in Stage 3.
                # For now just write 0s.
                #
                jumps.append(('rel', addr, op.jrel))
                arg = 0
            elif op.has_jabs:
                # Don't know the address yet. Will resolve that in Stage 3.
                # For now just write 0s.
                #
                jumps.append(('abs', addr, op.jabs))
                arg = 0
            elif op.has_arg:
                arg = op.arg

            if arg is not no_arg:
                if arg > 0xFFFF:
                    code.append(OP_EXTENDED_ARG.code)
                    code.append((arg >> 16) & 0xFF)
                    code.append((arg >> 24) & 0xFF)
                code.append(arg & 0xFF)
                code.append((arg >> 8) & 0xFF)

        # Stage 3.
        # Resolve jump addresses.
        #
        for jump in jumps:
            to = addrs[jump[2]]
            if jump[0] == 'rel':
                to -= (jump[1] + 3)

            if to > 0xFFFF:
                raise Exception('extended jumps are not currently supported')

            code[jump[1] + 1] = to & 0xFF
            code[jump[1] + 2] = (to >> 8) & 0xFF

        # Stage 4.
        # Assemble the new code object.

        co_code = bytes(code)
        co_lnotab = bytes(lnotab)

        co_varnames = tuple(co_varnames)
        co_names = tuple(co_names)
        co_cellvars = tuple(co_cellvars)
        co_freevars = tuple(co_freevars)
        co_consts = tuple(co_consts)

        return types.CodeType(co_argcount,
                              co_kwonlyargcount,
                              len(co_varnames),
                              self._calc_stack_size(),
                              self._calc_flags(),
                              co_code,
                              co_consts,
                              co_names,
                              co_varnames,
                              self.filename,
                              self.name,
                              self.firstlineno,
                              co_lnotab,
                              co_freevars,
                              co_cellvars)

    @classmethod
    def from_code(cls, pycode):
        '''Creates semantix code object out of python's one'''

        assert isinstance(pycode, types.CodeType)

        co_code = pycode.co_code
        cell_len = len(pycode.co_cellvars)
        n = len(co_code)
        i = 0

        table = {} # We use this to resolve jumps to real opcode objects in Stage 2
        ops = []

        OPMAP = opcodes.OPMAP

        lines = dict(dis.findlinestarts(pycode))

        freevars = OrderedSet()
        cellvars = OrderedSet()

        extended_arg = 0

        # Stage 1.
        # Transform serialized binary list of python opcodes to
        # a high level representation - list of opcode objects
        # defined in the 'opcodes' module
        #
        while i < n:
            op_cls = OPMAP[co_code[i]]
            op = op_cls()

            try:
                line = lines[i]
            except KeyError:
                pass
            else:
                op.lineno = line

            table[i] = op

            i += 1

            if op.has_arg:
                arg = op.arg = co_code[i] + co_code[i + 1] * 256 + extended_arg
                i += 2

                if op_cls is OP_EXTENDED_ARG:
                    extended_arg = arg << 16
                    # Don't need this opcode in our code object.  We'll write it back
                    # later in 'to_code' automatically if needed.
                    #
                    continue
                elif op_cls.has_jrel:
                    op.jrel = i + arg
                elif op_cls.has_jabs:
                    op.jabs = arg
                elif op_cls.has_name:
                    op.name = pycode.co_names[arg]
                elif op_cls.has_local:
                    op.local = pycode.co_varnames[arg]
                elif op_cls.has_const:
                    op.const = pycode.co_consts[arg]
                elif op_cls.has_free:
                    try:
                        op.cell = pycode.co_cellvars[arg]
                    except IndexError:
                        op.free = pycode.co_freevars[arg - cell_len]
                        freevars.add(op.free)
                    else:
                        cellvars.add(op.cell)

            ops.append(op)

        # Stage 2.
        # Resolve jump addresses to opcode objects.
        #
        for op in ops:
            if op.has_jrel:
                op.jrel = table[op.jrel]
            elif op.has_jabs:
                op.jabs = table[op.jabs]

        # Stage 3.
        # Unwind python's arguments mess.  All arguments names are stored in the
        # 'co_varnames' array, with the names of local variables too.

        varnames = pycode.co_varnames
        argcount = pycode.co_argcount

        argstop = argcount
        args = OrderedSet(varnames[:argstop])

        kwonlyargs = OrderedSet(varnames[argstop:argstop + pycode.co_kwonlyargcount])
        argstop += pycode.co_kwonlyargcount

        # Handle '*args' type of argument
        vararg = None
        if pycode.co_flags & CO_VARARGS:
            vararg = varnames[argstop]
            argstop += 1

        # Handle '**kwargs' type of argument
        varkwarg = None
        if pycode.co_flags & CO_VARKEYWORDS:
            varkwarg = varnames[argstop]
            argstop += 1

        varnames = OrderedSet(pycode.co_varnames[argstop:])

        # Docstring is just a first string element in the 'co_consts' tuple
        #
        docstring = None
        co_consts = pycode.co_consts
        if len(co_consts) and isinstance(co_consts[0], str):
            docstring = co_consts[0]

        obj = cls(ops,
                  vararg=vararg,
                  varkwarg=varkwarg,
                  newlocals=bool(pycode.co_flags & CO_NEWLOCALS),
                  filename=pycode.co_filename,
                  firstlineno=pycode.co_firstlineno,
                  name=pycode.co_name,
                  args=args,
                  kwonlyargs=kwonlyargs,
                  varnames=varnames,
                  freevars=freevars,
                  cellvars=cellvars,
                  docstring=docstring)

        return obj