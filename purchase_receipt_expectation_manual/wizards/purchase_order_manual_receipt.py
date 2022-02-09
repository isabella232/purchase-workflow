# Copyright 2021 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class WizardValidationError(ValidationError):
    """Specific exception for wizard data"""


class PurchaseOrderManualReceipt(models.TransientModel):
    _name = "purchase.order.manual.receipt.wizard"
    _description = "PO Manual Receipt Wizard"

    line_ids = fields.One2many(
        "purchase.order.manual.receipt.wizard.line",
        "wizard_id",
    )

    auto_confirm_picking = fields.Boolean(
        default=True, help="Automatically confirms the picking after creation."
    )

    checks_counter = fields.Integer(
        help="* If 0, it means no check has been run on wizard data.\n"
        "* If -1, it means no check is implemented on this wizard.\n"
        "If checks are implemented, anytime any of them is executed, this"
        " field increases by 1.",
    )

    checks_result = fields.Selection(
        [("success", "Success"), ("failure", "Failure")],
        default="success",
    )

    checks_result_msg = fields.Text(
        help="Stores error messages result from executed checks"
    )

    purchase_order_id = fields.Many2one(
        "purchase.order",
        required=True,
    )

    scheduled_date = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
    )

    @api.onchange("line_ids")
    def _onchange_lines_reset_counter(self):
        """Resets checks counter whenever lines are modified"""
        self.checks_counter = 0

    def open_form_view(self):
        self.ensure_one()
        return {
            "name": _("Manual Receipt"),
            "type": "ir.actions.act_window",
            "res_id": self.id,
            "res_model": "purchase.order.manual.receipt.wizard",
            "target": "new",
            "view_mode": "form",
        }

    def open_picking_form_view(self, picking):
        self.ensure_one()
        return {
            "name": _("Picking"),
            "type": "ir.actions.act_window",
            "res_id": picking.id,
            "res_model": "stock.picking",
            "view_mode": "form",
        }

    def button_check(self):
        """Runs checks on the wizard data, then opens the wizard again"""
        self.ensure_one()
        self._execute_checks()
        return self.open_form_view()

    @api.model
    def _get_checks(self) -> dict:
        """Returns checks to be executed on the wizard

        Checks are grouped per flag. Flag `all` must always be defined because
        is used as default fallback in method `_execute_checks()`.
        Hook method to be overridden by inheriting modules.
        """
        return {
            "pre-confirm-required": ["_check_lines_consistency"],
            "all": ["_check_lines_consistency", "_check_product_quantities"],
        }

    def _execute_pre_confirm_checks(self):
        """Performs pre-confirm required checks only"""
        self._execute_checks(flag="pre-confirm-required")

    def _execute_checks(self, flag: str = ""):
        """Executes checks on wizard data

        Checks to be executed are defined by `flag` according to method
        `_get_checks()`

        :param str flag: custom flag defining the checks type
        """
        self.ensure_one()
        errs = {}
        counter = self.checks_counter
        checks_by_flag = self._get_checks()
        for check in checks_by_flag.get(flag, checks_by_flag["all"]):
            try:
                # If method `check` is not properly defined, or it raises an
                # error different from `WizardValidationError`, the exception
                # won't be handled
                getattr(self, check)()
            except WizardValidationError as error:
                # Manage proper exception
                errs[check] = error.args[0]
            counter += 1
        vals = self._prepare_post_check_vals(errs, flag)
        vals.update({"checks_counter": counter})
        self.write(vals)

    def _prepare_post_check_vals(self, errors: dict, flag: str = "") -> dict:
        """Prepares `write` vals to update wizard after executing checks

        :param dict errors: dict mapping each check name to its error
        :param str flag: custom flag defining the checks type
        """
        res = "success"
        msg = ""
        if errors:
            res = "failure"
            msg = "\n\n".join(errors.values())
            if flag == "pre-confirm-required":
                msg = _("These checks cannot be skipped.\n\n").upper() + msg
        return {
            "checks_result": res,
            "checks_result_msg": msg,
        }

    def _check_lines_consistency(self):
        """Lines consistency check"""
        self.ensure_one()
        if not self.line_ids or any(line.qty < 0 for line in self.line_ids):
            raise WizardValidationError(
                _(
                    "Receipts must have at least 1 line and every line must"
                    " have strictly positive quantity."
                )
            )

    def _check_product_quantities(self):
        """Receivable/to receive quantities check"""
        self.ensure_one()
        if self.line_ids:
            prec = self.env["decimal.precision"].precision_get(
                "Product Unit of Measure"
            )
            mtr = [
                (pid, qtr, rq)
                for (pid, qtr, rq) in self._get_product_quantities_info()
                if float_compare(qtr, rq, prec) == 1
            ]
            if mtr:
                raise WizardValidationError(
                    self._format_check_product_quantities_msg(mtr)
                )

    def _get_product_quantities_info(self) -> list:
        """Returns list of triplet (prod.id, qty to receive, receivable qty)"""
        self.ensure_one()
        receivable = self._get_product_quantities_info_receivable()
        to_receive = self._get_product_quantities_info_to_receive()
        return [
            (pid, to_receive.get(pid, 0), receivable.get(pid, 0))
            for pid in set(to_receive.keys()).union(receivable.keys())
        ]

    def _get_product_quantities_info_receivable(self) -> dict:
        """Returns mapping {prod: receivable qty}

        Qty is retrieved from the purchase line's `manually_receivable_qty`
        field, so it's in product's PO UoM
        """
        self.ensure_one()
        receivable = defaultdict(float)
        for po_line in self.line_ids.purchase_line_id:
            prod, qty = po_line.product_id, po_line.manually_receivable_qty
            receivable[prod.id] += qty
        return receivable

    def _get_product_quantities_info_to_receive(self) -> dict:
        """Returns mapping {prod: qty to receive}

        Qty is retrieved from the wizard line's `qty` and is converted into
        product's PO UoM for consistency with
        `_get_product_quantities_info_receivable()` (this allows comparing data
        faster when the two mappings are used together)
        """
        self.ensure_one()
        to_receive = defaultdict(float)
        for line in self.line_ids:
            qty = line.qty
            from_uom = line.uom_id
            prod = line.product_id
            to_uom = prod.uom_po_id
            to_receive[prod.id] += from_uom._compute_quantity(qty, to_uom, round=False)
        return to_receive

    def _format_check_product_quantities_msg(self, mtr_data):
        """Formats warning if there's more qty to receive than receivable"""
        self.ensure_one()
        msg = [_("Qty to receive exceeds the receivable qty:")]
        for pid, q1, q2 in mtr_data:
            prod = self.env["product.product"].browse(pid)
            uom_name = prod.uom_po_id.name
            msg.append(
                _(
                    "- {prod_name}: to receive {q1} {uom_name},"
                    " receivable {q2} {uom_name}"
                ).format(prod_name=prod.name, q1=q1, q2=q2, uom_name=uom_name)
            )
        return "\n".join(msg)

    def button_confirm(self):
        """Confirms wizard data and creates new picking

        Before creating new pickings, pre-confirm checks are executed.
        Users are allowed to ignore warning messages but pre-confirm checks are
        mandatory to make the picking creation work correctly.
        """
        self.ensure_one()
        # Setting `checks_result` to "success" because the user is allowed to
        # ignore warnings; then, we'll run pre-confirm checks and, if any of
        # them fails, method `_execute_checks()` will reset `checks_result`
        self.checks_result = "success"
        self._execute_pre_confirm_checks()
        if self.checks_result != "success":
            # Some pre-confirm check failed: reopen the wizard
            return self.open_form_view()
        # Create picking and picking's open form view
        return self.open_picking_form_view(self._generate_picking())

    def _generate_picking(self):
        """Creates picking

        Also manages confirmation and validation if related fields are flagged
        """
        self.ensure_one()
        vals = self._get_picking_vals()
        vals["move_lines"] = [(0, 0, v) for v in self._get_move_vals_list()]
        picking = self.env["stock.picking"].create(vals)
        if self.auto_confirm_picking:
            picking.action_confirm()
        return picking

    def _get_picking_vals(self) -> dict:
        """Prepares `stock.picking.create()` vals"""
        self.ensure_one()
        order = self.purchase_order_id
        order = order.with_company(order.company_id)
        # Use `purchase.order` utilities to create picking data properly,
        # then just update the picking values according to wizard
        picking_vals = order._prepare_picking()
        picking_vals["scheduled_date"] = self.scheduled_date
        return picking_vals

    def _get_move_vals_list(self) -> list:
        """Returns list of `stock.move.create()` values"""
        self.ensure_one()
        return self.line_ids._get_move_vals_list()
