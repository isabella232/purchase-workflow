# Copyright 2014-2016 Numérigraphe SARL
# Copyright 2017 Eficent Business and IT Consulting Services, S.L.
# Copyright 2021 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import _, exceptions, models
from odoo.tools import float_is_zero


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    def write(self, values):
        res = super().write(values)
        if "product_qty" in values or "product_uom" in values:
            self._propagage_qty_to_moves()
        return res

    def _propagage_qty_to_moves(self):
        for line in self:
            if line.state != "purchase":
                continue
            moves = line.move_dest_ids | line.move_ids
            previous_qty = sum(moves.mapped("product_uom_qty"))
            new_qty = line.product_uom_qty
            # Do nothing is qty has been increased, since odoo handles this case
            if new_qty == previous_qty:
                continue
            # If qty has been decreased, cancel full moves if possible
            moves = (
                self.env["stock.move"]
                .search(
                    [
                        ("id", "in", moves.ids),
                        ("state", "not in", ("cancel", "done")),
                        ("product_id", "=", line.product_id.id),
                    ]
                )
                .sorted(lambda m: (m.product_uom_qty, m.quantity_done))
            )
            qty_to_remove = previous_qty - new_qty
            total_removable_qty = sum(
                [m.product_uom_qty - m.quantity_done for m in moves]
            )
            if qty_to_remove > total_removable_qty:
                exception_text = _(
                    "You cannot remove more that what remains to be done.\n"
                    "Max removable quantity {}."
                )
                raise exceptions.UserError(exception_text)
            while qty_to_remove:
                for move in moves:
                    # we cannot deduce more than the "not done" qty
                    removable_qty = move.product_uom_qty - move.quantity_done
                    # If removable_qty <= qty_to_remove, deduce removable_qty
                    if removable_qty <= qty_to_remove:
                        move.product_uom_qty -= removable_qty
                        qty_to_remove -= removable_qty
                    # Else, deduce qty_to_remove from it
                    else:
                        move.product_uom_qty -= qty_to_remove
                        qty_to_remove = 0
                    # if new move product_uom_qty is 0, cancel it
                    if float_is_zero(move.product_uom_qty, line.product_uom.rounding):
                        move._action_cancel()
