import sqlalchemy as _sqlalchemy
import sqlalchemy.orm as _orm

from arrow import Arrow as _Arrow
from dataclasses import dataclass as _dataclass
from sqlalchemy import Engine as _Engine
from sqlalchemy.orm import DeclarativeBase as _DeclarativeBase, \
    Mapped as _Mapped
from sqlalchemy_utils import ArrowType as _ArrowType
from typing import List as _List, Optional as _Optional

from ..types import Location as _Location


def create_tables(engine: _Engine) -> None:
    """Create the relevant tables in the database.

    Raises:
        DatabaseError: If the database is corrupted.

    Args:
        engine (Engine): The engine to use for the creation of the
            tables.
    """
    _Base.metadata.create_all(engine)


class _Base(_DeclarativeBase):
    """Base class for objects stored in the database, defining the ORM
    root.
    """
    pass


@_dataclass
class TestFile(_Base):
    """Defines how the test file information is stored in the
    database.
    """

    __test__ = False  # This is not a pytest test class.

    __tablename__ = "test_file"

    id: _Mapped[int] = _orm.mapped_column(primary_key=True)
    """The id."""

    path: _Mapped[str] = _orm.mapped_column(unique=True, index=True)
    """The path of the file as defined in the item locations."""

    last_hash: _Mapped[_Optional[bytes]] = _orm.mapped_column()
    """The last known hash of the file, if it was recorded."""

    items: _Mapped[_List["TestItem"]] = _orm.relationship(
        back_populates="file"
    )
    """The test items contained in this file."""


@_dataclass
class TestItem(_Base):
    """Defines how the test item information is stored in the
    database.
    """

    __test__ = False  # This is not a pytest test class.

    __tablename__ = "test_item"

    __table_args__ = (
        _sqlalchemy.UniqueConstraint("file_id", "lineno", "testname"),
    )

    id: _Mapped[int] = _orm.mapped_column(primary_key=True)
    """The id."""

    file_id: _Mapped[int] = _orm.mapped_column(
        _sqlalchemy.ForeignKey("test_file.id")
    )

    file: _Mapped[TestFile] = _orm.relationship(back_populates="items")
    """The file in which the item was found."""

    lineno: _Mapped[_Optional[int]] = _orm.mapped_column(nullable=True)
    """The line where the test is found."""

    testname: _Mapped[str] = _orm.mapped_column(nullable=False)
    """The name of the test."""

    last_run: _Mapped[_Arrow] = _orm.mapped_column(
        nullable=False, type_=_ArrowType
    )
    """The date and time the test was last run."""

    @property
    def location(self) -> _Location:
        """The location of the test.

        Returns:
            Location: The location of the test.
        """
        return (self.file.path, self.lineno, self.testname)
