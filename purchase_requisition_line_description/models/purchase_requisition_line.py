# Copyright 2021 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class PurchaseRequisitionLine(models.Model):
    _inherit = "purchase.requisition.line"

    name = fields.Text()

    @api.onchange('product_id')
    def _onchange_product_id(self):
        # to format name into: "[product_code] product_name"
        res = super()._onchange_product_id()
        desc = (self.name or "")
        if self.product_id:
            product_lang = self.product_id.with_context(
                lang=self.requisition_id.purchase_ids.partner_id.lang,
                partner_id=self.requisition_id.purchase_ids.partner_id.id,
            )
            vendor_data = product_lang.seller_ids.filtered(
                lambda a: a.product_id == self.product_id
                and (a.product_name
                or a.product_code)
            )[0]
            if vendor_data and vendor_data.product_code:
                desc += '[' + vendor_data.product_code + '] '
            if vendor_data and vendor_data.product_name:
                desc += vendor_data.product_name + '\n'
            self.name = desc
        return res
