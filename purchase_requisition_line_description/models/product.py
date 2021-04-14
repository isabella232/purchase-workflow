# Copyright 2021 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model
    def _name_search(
        self, name, args=None, operator='ilike', limit=100, name_get_uid=None
    ):
        if name and self.env.context.get('vendor_data_search'):
            positive_operators = ['=', 'ilike', '=ilike', 'like', '=like']
            product_ids = []
            if operator in positive_operators:
                product_ids = self._search(
                    [('seller_ids.product_code', '=', name)] + args,
                    limit=limit,
                    access_rights_uid=name_get_uid,
                )
                if not product_ids:
                    product_ids = self._search(
                        [('seller_ids.product_name', '=', name)] + args,
                        limit=limit,
                        access_rights_uid=name_get_uid,
                    )
        else:
            product_ids = self._search(
                args, limit=limit, access_rights_uid=name_get_uid
            )
        return self.browse(product_ids).name_get()
