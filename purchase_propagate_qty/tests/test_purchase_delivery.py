# Copyright 2014-2016 Numérigraphe SARL
# Copyright 2017 Eficent Business and IT Consulting Services, S.L.
# Copyright 2021 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo.exceptions import UserError
from odoo.tests.common import SavepointCase


class TestQtyUpdate(SavepointCase):
    at_install = False
    post_install = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.product_model = cls.env["product.product"]

        # Create products:
        p1 = cls.product1 = cls.product_model.create(
            {"name": "Test Product 1", "type": "product", "default_code": "PROD1"}
        )
        p2 = cls.product2 = cls.product_model.create(
            {"name": "Test Product 2", "type": "product", "default_code": "PROD2"}
        )
        cls.date_planned = "2020-04-30 12:00:00"
        partner = cls.env["res.partner"].create({"name": "supplier"})
        cls.po = cls.env["purchase.order"].create(
            {
                "partner_id": partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": p1.id,
                            "product_uom": p1.uom_id.id,
                            "name": p1.name,
                            "price_unit": p1.standard_price,
                            "date_planned": cls.date_planned,
                            "product_qty": 42.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "product_id": p2.id,
                            "product_uom": p2.uom_id.id,
                            "name": p2.name,
                            "price_unit": p2.standard_price,
                            "date_planned": cls.date_planned,
                            "product_qty": 12.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "product_id": p1.id,
                            "product_uom": p1.uom_id.id,
                            "name": p1.name,
                            "price_unit": p1.standard_price,
                            "date_planned": cls.date_planned,
                            "product_qty": 1.0,
                        },
                    ),
                ],
            }
        )
        cls.po.button_confirm()

    def test_purchase_line_qty_decrease(self):
        """decrease qty on confirmed po -> decreased reception"""
        line1 = self.po.order_line[0]
        move1 = self.env["stock.move"].search([("purchase_line_id", "=", line1.id)])
        line1.write({"product_qty": 30})
        self.assertEqual(move1.product_uom_qty, 30)

    def test_purchase_line_unlink(self):
        """decrease qty on confirmed po -> decreased reception"""
        line1 = self.po.order_line[0]
        exception_regex = (
            r"Cannot delete a purchase order line which is in state 'purchase'."
        )
        with self.assertRaisesRegex(UserError, exception_regex):
            line1.unlink()

    def test_purchase_line_qty_decrease_to_zero(self):
        """decrease qty on confirmed po -> decreased reception"""
        line1 = self.po.order_line[0]
        move1 = self.env["stock.move"].search([("purchase_line_id", "=", line1.id)])
        line1.write({"product_qty": 0})
        self.assertEqual(move1.product_uom_qty, 0)
        self.assertEqual(move1.state, "cancel")

    def test_purchase_line_splitted_move(self):
        # Add qty, create a new move with the diff
        line1 = self.po.order_line[0]
        move1 = self.env["stock.move"].search([("purchase_line_id", "=", line1.id)])
        self.assertEqual(len(move1), 1)
        line1.write({"product_qty": 64})
        self.assertEqual(move1.product_uom_qty, 64)
        # split the move
        move1._split(22)
        moves = self.env["stock.move"].search([("purchase_line_id", "=", line1.id)])
        self.assertEqual(len(moves), 2)
        self.assertEqual(moves.mapped("product_uom_qty"), [42.0, 22.0])
        # Then, decrease 11
        line1.write({"product_qty": 53})
        self.assertEqual(moves.mapped("product_uom_qty"), [42.0, 11.0])
        # Again, decrease 11
        line1.write({"product_qty": 42})
        self.assertEqual(moves.mapped("product_uom_qty"), [42.0, 0.0])
        active_move = moves.filtered(lambda m: m.state != "cancel")
        inactive_move = moves.filtered(lambda m: m.state == "cancel")
        self.assertEqual(active_move.product_uom_qty, 42)
        self.assertEqual(inactive_move.product_uom_qty, 0)

    def test_purchase_line_splitted_move_w_reserved_qty(self):
        # Add qty, create a new move with the diff
        line1 = self.po.order_line[0]
        move1 = self.env["stock.move"].search([("purchase_line_id", "=", line1.id)])
        self.assertEqual(len(move1), 1)
        line1.with_context(unittests=True).write({"product_qty": 64})
        self.assertEqual(move1.product_uom_qty, 64)
        # split the move
        move1._split(22)
        moves = self.env["stock.move"].search([("purchase_line_id", "=", line1.id)])
        move2 = moves - move1
        # reserve 11 qty
        self.env["stock.move.line"].create(
            dict(move2._prepare_move_line_vals(), qty_done=11)
        )
        self.assertEqual(move2.quantity_done, 11)
        line1.write({"product_qty": 60})
        self.assertEqual(moves.mapped("product_uom_qty"), [42.0, 18.0])
        # We cannot remove more than 11 on move2, deduce the max from it,
        # then deduce from move1
        line1.write({"product_qty": 50})
        self.assertEqual(moves.mapped("product_uom_qty"), [39.0, 11.0])
        # We should not be able to set a qty < to 11, since 11 products are reserved
        with self.assertRaises(UserError):
            line1.write({"product_qty": 5})
        # with 11, move1 should be cancelled
        line1.write({"product_qty": 11})
        self.assertEqual(move1.product_uom_qty, 0.0)
        self.assertEqual(move1.state, "cancel")
        self.assertEqual(move2.product_uom_qty, 11.0)
