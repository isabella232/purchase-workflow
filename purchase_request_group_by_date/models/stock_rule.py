# Copyright 2018-2020 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from datetime import datetime

from odoo import api, fields, models


class StockRule(models.Model):
    _inherit = "stock.rule"

    company_group_purchase_request = fields.Boolean(
        related="company_id.group_purchase_request"
    )

    # override to change returned domain based on company settings
    @api.model
    def _make_pr_get_domain(self, values):
        domain = super()._make_pr_get_domain(values)
        if self.company_group_purchase_request:
            domain += ("date_start", "=", datetime.today().date())
            gpo = self.group_propagation_option
            group_id = (
                (gpo == "fixed" and self.group_id.id)
                or (gpo == "propagate" and values["group_id"].id)
                or False
            )
            if group_id:
                domain += (("group_id", "=", group_id),)
        return domain

    # override to change existing pr handling
    def create_purchase_request(self, procurement_group):
        if self.company_group_purchase_request:
            procurement = procurement_group[0]
            rule = procurement_group[1]
            purchase_request_model = self.env["purchase.request"]
            purchase_request_line_model = self.env["purchase.request.line"]
            cache = {}
            pr = self.env["purchase.request"]
            domain = rule._make_pr_get_domain(procurement.values)
            if domain in cache:
                pr = cache[domain]
            elif domain:
                pr = (
                    self.env["purchase.request"]
                    .search(domain)
                    .filtered(
                        lambda x: procurement.product_id
                        in x.line_ids.mapped("product_id")
                    )
                )
                pr = pr[0] if pr else False
                cache[domain] = pr
            if not pr:
                request_data = rule._prepare_purchase_request(
                    procurement.origin, procurement.values
                )
                pr = purchase_request_model.create(request_data)
                cache[domain] = pr
            elif not pr.origin or procurement.origin not in pr.origin.split(", "):
                if pr.origin:
                    if procurement.origin:
                        pr.write({"origin": pr.origin + ", " + procurement.origin})
                    else:
                        pr.write({"origin": pr.origin})
                else:
                    pr.write({"origin": procurement.origin})
            # Create Line
            request_line_data = rule._prepare_purchase_request_line(pr, procurement)
            # check if request has lines for same product and data
            # if yes, update qty instead of creating new line
            same_product_date_request_line = pr.line_ids.filtered_domain(
                [
                    ("product_id", "=", request_line_data["product_id"]),
                    ("date_required", "=", request_line_data["date_required"].date()),
                    (
                        "purchase_state",
                        "=",
                        False,
                    ),  # avoid updating if there is RFQ or PO linked
                ],
            )
            if same_product_date_request_line:
                new_product_qty = (
                    same_product_date_request_line.product_qty
                    + request_line_data["product_qty"]
                )
                same_product_date_request_line.write({"product_qty": new_product_qty})
            else:
                # Create Line
                purchase_request_line_model.create(request_line_data)
        else:
            super().create_purchase_request(procurement_group)