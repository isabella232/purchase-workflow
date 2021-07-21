# Copyright 2021 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models
from odoo.tools import float_is_zero


class StockMove(models.Model):
    _inherit = "stock.move"

    def _deduce_qty(self, qty_to_remove, rounding):
        """Deduce the provided qty with respect to done qties."""
        for move in self:
            if qty_to_remove == 0:
                break
            # we cannot deduce more than the "not done" qty
            removable_qty = move._get_removable_qty()
            # If removable_qty <= qty_to_remove, deduce removable_qty
            if removable_qty <= qty_to_remove:
                move.product_uom_qty -= removable_qty
                qty_to_remove -= removable_qty
            # Else, deduce qty_to_remove from it
            else:
                move.product_uom_qty -= qty_to_remove
                qty_to_remove = 0
            # if new move product_uom_qty is 0, cancel it
            if float_is_zero(move.product_uom_qty, rounding):
                move._action_cancel()

    def _get_removable_qty(self):
        return sum([move.product_uom_qty - move.quantity_done for move in self])
