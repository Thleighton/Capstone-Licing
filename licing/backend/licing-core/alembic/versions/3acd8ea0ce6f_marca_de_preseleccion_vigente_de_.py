"""Marca de preseleccion vigente de licitaciones

Revision ID: 3acd8ea0ce6f
Revises: a13c4d7e9f20
Create Date: 2026-11-14 23:51:07.469678

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3acd8ea0ce6f'
down_revision: Union[str, None] = 'a13c4d7e9f20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('licitacion', sa.Column('preseleccion', postgresql.JSONB(none_as_null=True), nullable=True))


def downgrade() -> None:
    op.drop_column('licitacion', 'preseleccion')
