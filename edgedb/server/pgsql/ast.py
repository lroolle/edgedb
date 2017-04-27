##
# Copyright (c) 2008-present MagicStack Inc.
# All rights reserved.
#
# See LICENSE for details.
##


import enum
import typing

from edgedb.lang.common import ast
from edgedb.lang.edgeql import ast as qlast
from edgedb.lang.ir import ast as irast


# The structure of the nodes mostly follows that of Postgres'
# parsenodes.h and primnodes.h, but only with fields that are
# relevant to parsing and code generation.
#
# Certain nodes have EdgeDB-specific fields used by the
# compiler.


class Base(ast.AST):
    def __repr__(self):
        return f'<pg.{self.__class__.__name__} at 0x{id(self):x}>'


class _Ref(Base):

    node: Base

    def __repr__(self):
        return f'<pg.{self.__class__.__name__} -> {self.node!r}>'


class Alias(Base):
    """Alias for a range variable."""

    aliasname: str              # aliased relation name
    colnames: typing.List[str]  # optional list of column aliases


class Keyword(Base):
    """An SQL keyword that must be output without quoting."""

    name: str                   # Keyword name


class EdgeQLPathInfo(Base):
    """A general mixin providing EdgeQL-specific metadata on certain nodes."""

    # Ignore the below fields in AST visitor/transformer.
    __ast_meta__ = {'path_bonds'}

    path_bonds: typing.Set[irast.PathId]  # A subset of paths
                                          # necessary to perform joining.


class BaseRangeVar(Base):
    """Range variable, used in FROM clauses."""

    alias: Alias
    nullable: bool

    @property
    def path_id(self):
        return self.query.path_id

    @property
    def path_outputs(self):
        return self.query.path_outputs

    @property
    def path_namespace(self):
        return self.query.path_namespace

    @property
    def path_bonds(self):
        return self.query.path_bonds

    @property
    def inner_path_bonds(self):
        return self.query.inner_path_bonds


RangeTypes = typing.Union[BaseRangeVar, _Ref]


class BaseRelation(Base):
    pass


class Relation(BaseRelation, EdgeQLPathInfo):
    """Regular relation."""

    catalogname: str
    schemaname: str
    relname: str


class RangeVar(BaseRangeVar):
    """Relation range variable, used in FROM clauses."""

    relation: BaseRelation
    inhopt: bool

    @property
    def query(self):
        if isinstance(self.relation, CommonTableExpr):
            return self.relation.query
        else:
            return self.relation


class TypeName(Base):
    """Type in definitions and casts."""

    name: typing.Tuple[str, ...]    # Type name
    setof: bool                     # SET OF?
    typmods: list                   # Type modifiers
    array_bounds: list              # Array bounds


class Star(Base):
    """'*' representing all columns of a table or compound field."""


class ColumnRef(Base):
    """Specifies a reference to a column."""

    name: typing.List[typing.Union[str, Star]]  # Column name list
    nullable: bool                              # Whether NULL is possible
    grouped: bool                               # Whether the col is grouped
    weak: bool                                  # Whether the col is a weak
                                                # path bond.

    def __repr__(self):
        return (
            f'<pg.{self.__class__.__name__} '
            f'name={".".join(self.name)!r} at 0x{id(self):x}>'
        )


ColumnRefTypes = typing.Union[ColumnRef, _Ref]


class ParamRef(Base):
    """Query parameter ($1..$n)."""

    number: int                         # Number of the parameter


class ResTarget(Base):
    """Query result target."""

    name: str                       # column name (optional)
    indirection: list               # subscripts, field names and '*'
    val: Base                       # value expression to compute


class UpdateTarget(Base):
    """Query update target."""

    name: str                       # column name (optional)
    val: Base                       # value expression to assign


class InferClause(Base):

    index_elems: list               # IndexElems to infer unique index
    where_clause: Base              # Partial-index predicate
    conname: str                    # Constraint name


class OnConflictClause(Base):

    action: str
    infer: InferClause
    target_list: list
    where: Base


class CommonTableExpr(BaseRelation):

    name: str                       # Query name (unqualified)
    aliascolnames: list             # Optional list of column names
    query: Base                     # The CTE query
    recursive: bool                 # True if this CTE is recursive

    def __repr__(self):
        return (
            f'<pg.{self.__class__.__name__} '
            f'name={self.name!r} at 0x{id(self):x}>'
        )


class Query(BaseRelation, EdgeQLPathInfo):
    """Generic superclass representing a query."""

    # Ignore the below fields in AST visitor/transformer.
    __ast_meta__ = {'ptr_join_map', 'path_rvar_map', 'path_namespace',
                    'path_outputs', 'view_path_id_map', 'as_type', 'argnames'}

    ptr_join_map: dict              # Map of RangeVars corresponding to pointer
                                    # relations.

    path_rvar_map: typing.Dict[irast.PathId, BaseRangeVar]
                                    # Map of RanveVars corresponding to paths.
    path_namespace: dict
                                    # Map of col refs corresponding to paths.
    path_outputs: dict              # Map of res target names corresponding
                                    # to paths.

    as_type: irast.PathId

    argnames: typing.Dict[str, int]

    view_path_id_map: typing.Dict[irast.PathId, irast.PathId]

    ctes: typing.List[CommonTableExpr]


class DML(Base):
    """Generic superclass for INSERT/UPDATE/DELETE statements."""

    relation: RangeTypes              # Target relation to perform the
                                      # operation on
    returning_list: typing.List[ResTarget]  # List of expressions returned


class InsertStmt(Query, DML):

    cols: typing.List[ColumnRefTypes]  # (optional) list of target column names
    select_stmt: Query              # source SELECT/VALUES or None
    on_conflict: OnConflictClause   # ON CONFLICT clause


class UpdateStmt(Query, DML):

    targets: typing.List[UpdateTarget]          # The UPDATE target list
    where_clause: Base                          # WHERE clause
    from_clause: typing.List[RangeTypes]        # optional FROM clause


class DeleteStmt(Query, DML):
    where_clause: Base                          # WHERE clause
    using_clause: typing.List[RangeTypes]       # optional USING clause


class SelectStmt(Query):

    distinct_clause: list               # List of DISTINCT ON expressions,
                                        # empty list for DISTINCT ALL
    target_list: typing.List[ResTarget] # The target list
    from_clause: typing.List[RangeTypes]  # The FROM clause
    where_clause: Base                  # The WHERE clause
    group_clause: typing.List[Base]     # GROUP BY clauses
    having: Base                        # HAVING expression
    window_clause: typing.List[Base]    # WINDOW window_name AS(...),
    values: typing.List[Base]           # List of ImplicitRow's in
                                        # a VALUES query

    sort_clause: typing.List[Base]      # ORDER BY clause
    limit_offset: Base                  # OFFSET expression
    limit_count: Base                   # LIMIT expression
    locking_clause: list                # FOR UPDATE clause

    op: str                             # Set operation type
    all: bool                           # ALL modifier
    larg: Query                         # Left operand of set op
    rarg: Query                         # Right operand of set op,


class ExprKind(enum.IntEnum):
    OP = enum.auto()


class Expr(Base):
    """Infix, prefix, and postfix expressions."""

    kind: ExprKind      # Operator kind
    name: str           # Possibly-qualified name of operator
    lexpr: Base         # Left argument, if any
    rexpr: Base         # Right argument, if any


class Constant(Base):
    """A literal constant."""

    val: object         # Constant value


class LiteralExpr(Base):
    """A literal expression."""

    expr: str           # Expression text


class TypeCast(Base):
    """A CAST expression."""

    arg: Base               # Expression being casted
    type_name: TypeName     # Target type


class CollateClause(Base):
    """A COLLATE expression."""

    arg: Base               # Input expression
    collname: str           # Possibly-qualified collation name


class FuncCall(Base):
    name: typing.Tuple[str, ...]    # Function name
    args: typing.List[Base]         # List of arguments
    agg_order: typing.List[Base]    # ORDER BY
    agg_filter: Base                # FILTER clause
    agg_star: bool                  # Argument list is '*'
    agg_distinct: bool              # Arguments were labeled DISTINCT
    over: Base                      # OVER clause, if any
    with_ordinality: bool = False


class Indices(Base):
    """Array subscript or slice bounds."""

    is_slice: bool      # True, if slice
    lidx: Base          # Lower bound, if any
    ridx: Base          # Upper bound if any


class Indirection(Base):
    """Field and/or array element indirection."""

    arg: Base               # Indirection subject
    indirection: list       # Subscripts and/or field names and/or '*'


class ArrayExpr(Base):
    """ARRAY[] construct."""

    elements: typing.List[Base]     # array element expressions


class MultiAssignRef(Base):
    """UPDATE (a, b, c) = row-valued-expr."""

    source: Base                          # row-valued expression
    columns: typing.List[ColumnRefTypes]  # list of columns to assign to


class SortBy(Base):
    """ORDER BY clause element."""

    node: Base                  # expression to sort on
    dir: qlast.SortOrder        # ASC/DESC/USING/default
    nulls: qlast.NonesOrder     # NULLS FIRST/LAST


class WindowDef(Base):
    """WINDOW and OVER clauses."""

    name: str                   # window name
    refname: str                # referenced window name, if any
    partition_clause: typing.List[Base]     # PARTITION BY expr list
    order_clause: typing.List[SortBy]       # ORDER BY
    frame_options: list         # Window frame options
    start_offset: Base          # expression for starting bound, if any
    end_offset: Base            # expression for ending ound, if any


class RangeSubselect(BaseRangeVar):
    """Subquery appearing in FROM clauses."""

    lateral: bool
    subquery: BaseRelation

    @property
    def query(self):
        if isinstance(self.subquery, CommonTableExpr):
            return self.subquery.query
        else:
            return self.subquery


class ColumnDef(Base):

    name: str                   # name of column
    typename: TypeName          # type of column
    default_expr: Base          # default value, if any
    coll_clause: Base           # COLLATE clause, if any


class RangeFunction(BaseRangeVar):

    lateral: bool
    ordinality: Base
    is_rowsfrom: bool
    functions: typing.List[FuncCall]
    coldeflist: typing.List[ColumnDef]  # list of ColumnDef nodes to describe
                                        # result of the function returning
                                        # RECORD.


class JoinExpr(BaseRangeVar):
    type: str                           # Type of join

    larg: Base                          # Left subtree
    rarg: Base                          # Right subtree
    using_clause: typing.List[Base]     # USING clause, if any
    quals: Base                         # Qualifiers on join, if any

    def copy(self):
        result = self.__class__()
        result.copyfrom(self)
        return result

    def copyfrom(self, other):
        self.larg = other.larg
        self.rarg = other.rarg
        self.quals = other.quals
        self.type = other.type


class SubLinkType(enum.IntEnum):
    EXISTS = enum.auto()
    ALL = enum.auto()
    ANY = enum.auto()


class SubLink(Base):
    """Subselect appearing in an expression."""

    type: SubLinkType               # Type of sublink
    expr: Base                      # Sublink expression


class RowExpr(Base):
    """A ROW() expression."""

    args: typing.List[Base]         # The fields.


class ImplicitRowExpr(Base):
    """A (a, b, c) expression."""

    args: typing.List[Base]         # The fields.


class CoalesceExpr(Base):
    """A COALESCE() expression."""

    args: typing.List[Base]         # The arguments.


class NullTest(Base):
    """IS [NOT] NULL."""

    arg: Base                       # Input expression,
    negated: bool                   # NOT NULL?


class CaseWhen(Base):

    expr: Base                      # Condition expression
    result: Base                    # subsitution result


class CaseExpr(Base):

    arg: Base                       # Equality comparison argument
    args: typing.List[CaseWhen]     # List of WHEN clauses
    defresult: Base                 # ELSE clause


class PgSQLOperator(ast.ops.Operator):
    pass


class PgSQLComparisonOperator(PgSQLOperator, ast.ops.ComparisonOperator):
    pass


LIKE = PgSQLComparisonOperator('~~')
NOT_LIKE = PgSQLComparisonOperator('!~~')
ILIKE = PgSQLComparisonOperator('~~*')
NOT_ILIKE = PgSQLComparisonOperator('!~~*')
SIMILAR_TO = PgSQLComparisonOperator('~')
NOT_SIMILAR_TO = PgSQLComparisonOperator('!~')
IS_DISTINCT = PgSQLComparisonOperator('IS DISTINCT')
IS_NOT_DISTINCT = PgSQLComparisonOperator('IS NOT DISTINCT')
IS_OF = PgSQLComparisonOperator('IS OF')
IS_NOT_OF = PgSQLComparisonOperator('IS NOT OF')


class PgSQLSetOperator(PgSQLOperator):
    pass


UNION = PgSQLSetOperator('UNION')
INTERSECT = PgSQLSetOperator('INTERSECT')
EXCEPT = PgSQLSetOperator('EXCEPT')

SortAsc = qlast.SortAsc
SortDesc = qlast.SortDesc
SortDefault = qlast.SortDefault

NullsFirst = qlast.NonesFirst
NullsLast = qlast.NonesLast
