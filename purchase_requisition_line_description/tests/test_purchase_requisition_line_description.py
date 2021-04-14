# Copyright 2021 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo.tests import common
from odoo import fields


class TestPurchaseRequisitionLineDescription(common.SavepointCase):
    @classmethod
    def setUpClass(cls):
        super(TestPurchaseRequisitionLineDescription, cls).setUpClass()
        partner = cls.env['res.partner'].create({
            'name': 'Test partner',
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Product',
            'standard_price': 10,
            'description_purchase': 'description for purchase',
        })
        cls.purchase = cls.env['purchase.requisition'].create({
            'partner_id': partner.id,
            'line_ids': [(0, 0, {
                'product_id': cls.product.id,
                'name': cls.product.name,
                'price_unit': 79.80,
                'product_qty': 15.0,
                'product_uom': cls.env.ref('uom.product_uom_unit').id,
                'date_planned': fields.Date.today(),
            })]
        })

    def test_onchange_product_id(self):
        self.assertEqual(self.product.name, self.purchase.line_ids[0].name)
        # Test onchange product
        self.purchase.line_ids[0]._onchange_product_id()
        self.assertEqual(
            self.purchase.line_ids[0].name, self.product.name+'\n'+self.product.description_purchase)