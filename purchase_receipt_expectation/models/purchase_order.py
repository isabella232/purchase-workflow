# Copyright 2021 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from collections import defaultdict

from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    receipt_expectation = fields.Selection(
        [("automatic", "Automatic")],
        help="Defines how reception pickings are managed when the order is"
        " approved.\nDefault value is 'automatic', which means the"
        " picking will be created following the standard Odoo workflow.\n"
        "New values added to this selection also require the definition"
        " of methods that manage such values.\nThese methods must be"
        " named `_create_picking_for_<value>_receipt_expectation`.",
        default="automatic",
        required=True,
    )

    def _create_picking(self):
        if self.env.context.get("standard_create_picking"):
            # Shortcut; also avoids recursion errors
            return super()._create_picking()
        groups = defaultdict(list)
        for order in self:
            groups[order.receipt_expectation].append(order.id)
        for exp, order_ids in groups.items():
            orders = self.browse(order_ids)
            method = "_create_picking_for_%s_receipt_expectation" % exp
            try:
                getattr(orders, method)()
            except AttributeError as err:
                msg = "Method `%s.%s()` not implemented" % (self._name, method)
                raise NotImplementedError(msg) from err
        return True

    def _create_picking_for_automatic_receipt_expectation(self):
        """Automatic => standard picking creation workflow"""
        orders = self.with_context(standard_create_picking=True)
        return orders._create_picking()
