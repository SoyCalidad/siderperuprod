from odoo.exceptions import UserError
from odoo import models, fields, api, _


class StockPicking(models.Model):
    _inherit = 'stock.picking'
    move_type = fields.Selection(selection_add=[
        ('out_invoice', 'Customer Invoice'), ('in_invoice', 'Vendor Bill')
    ], ondelete={'out_invoice': 'set default', 'in_invoice': 'set default'})


class InvoiceStockMove(models.Model):
    _inherit = 'account.move'

    # @api.model
    def _default_picking_receive(self):
        type_obj = self.env['stock.picking.type']
        company_id = self.env.context.get('company_id') or self.env.company.id
        types = type_obj.search(
            [('code', '=', 'incoming'), ('warehouse_id.company_id', '=', company_id)], limit=1)
        if not types:
            types = type_obj.search(
                [('code', '=', 'incoming'), ('warehouse_id', '=', False)])
        return types[:1]

    # @api.model
    def _default_picking_transfer(self):
        type_obj = self.env['stock.picking.type']
        company_id = self.env.context.get('company_id') or self.env.company.id
        types = type_obj.search(
            [('code', '=', 'outgoing'), ('warehouse_id.company_id', '=', company_id)], limit=1)
        if not types:
            types = type_obj.search(
                [('code', '=', 'outgoing'), ('warehouse_id', '=', False)])
        return types[:4]

    def _compute_deliver_status(self):
        if self.picking_count > 0:
            if self.name:
                picking_type_state = self.env['stock.picking'].search(
                    [('origin', '=', self.name), ('state', '!=', 'done'), ('partner_id', '=', self.partner_id.id)])
                if picking_type_state:
                    self.deliver_status = 'partially'
                else:
                    self.deliver_status = 'delivered'

    def _compute_shipment_status(self):
        if self.picking_shipment_count > 0:
            if self.name:
                picking_type_state = self.env['stock.picking'].search(
                    [('origin', '=', self.name), ('state', '!=', 'done')])
                if picking_type_state:
                    self.shipment_status = 'partially'
                else:
                    self.shipment_status = 'received'

    stock_picking = fields.Boolean(
        "Stock Picking From Invoice", related="company_id.stock_picking")
    stock_picking_bill = fields.Boolean(
        "Stock Picking From Bills", related="company_id.stock_picking_bill")

    picking_count = fields.Integer(
        string="Count", compute='_compute_picking_count')
    picking_shipment_count = fields.Integer(
        string="Count", compute='_compute_shipment_count')
    invoice_picking_id = fields.Many2one('stock.picking', string="Picking Id")
    picking_type_id = fields.Many2one('stock.picking.type', 'Picking Type', required=True,
                                      default=_default_picking_receive,
                                      help="This will determine picking type of incoming shipment")
    picking_transfer_id = fields.Many2one('stock.picking.type', 'Deliver To', required=True,
                                          default=_default_picking_transfer,
                                          help="This will determine picking type of outgoing shipment")
    picking_deliver = fields.Boolean(
        string="Deliver", compute='_compute_picking_deliver')
    picking_deliver_bill = fields.Boolean(
        string="Deliver", compute='_compute_picking_deliver_bill')
    deliver_no = fields.Boolean(
        string="Deliver No", compute='_compute_picking_deliver_no')
    deliver_shipment_no = fields.Boolean(
        string="Deliver No", compute='_compute_shipment_deliver_no')
    deliver_status = fields.Selection([
        ('delivered', 'Delivered'),
        ('partially', 'Partially Delivered'),
    ], string='Deliver Status', readonly=True, track_visibility='always')
    shipment_status = fields.Selection([
        ('received', 'Received'),
        ('partially', 'Partially Received'),
    ], string='Shipment Status', readonly=True, track_visibility='always')

    states = fields.Selection([
        ('draft', 'Draft'),
        ('proforma', 'Pro-forma'),
        ('proforma2', 'Pro-forma'),
        ('open', 'Open'),
        ('paid', 'Paid'),
        ('cancel', 'Cancelled'),
        ('done', 'Received'),
    ], string='Status', index=True, readonly=True, default='draft',
        track_visibility='onchange', copy=False)

    def action_stock_receive(self):
        if self.company_id.stock_picking_bill == True:
            for order in self:
                if not order.invoice_line_ids:
                    raise UserError(_('Please create some invoice lines.'))
                if not self.name:
                    raise UserError(_('Please Validate invoice.'))
                if not self.invoice_picking_id:
                    pick = {
                        'picking_type_id': self.picking_type_id.id,
                        'partner_id': self.partner_id.id,
                        'origin': self.name,
                        'location_dest_id': self.picking_type_id.default_location_dest_id.id,
                        'location_id': self.partner_id.property_stock_supplier.id
                    }
                    picking = self.env['stock.picking'].create(pick)
                    self.invoice_picking_id = picking.id
                    moves = order.invoice_line_ids.filtered(lambda r: r.product_id.type in [
                                                            'product', 'consu'])._create_stock_moves(picking)
                    move_ids = moves._action_confirm()
                    move_ids._action_assign()
        else:
            return True
        if self.picking_shipment_count > 0:
            if self.name:
                picking_type_state = self.env['stock.picking'].search(
                    [('origin', '=', self.name), ('state', '!=', 'done')])
                if picking_type_state:
                    self.shipment_status = 'partially'
                else:
                    self.shipment_status = 'received'

    def _compute_picking_count(self):
        if self.name:
            picking_type_ids = self.env['stock.picking'].search(
                [('origin', '=', self.name),('partner_id','=',self.partner_id.id)])
            if picking_type_ids:
                self.picking_count = len(picking_type_ids)
            else:
                self.picking_count = 0

    def _compute_shipment_count(self):
        if self.name:
            picking_type_ids = self.env['stock.picking'].search(
                [('origin', '=', self.name)])
            if picking_type_ids:
                self.picking_shipment_count = len(picking_type_ids)
            else:
                self.picking_shipment_count = 0

    def _compute_picking_deliver_bill(self):
        if self.company_id.stock_picking_bill == True:
            self.picking_deliver_bill = True
        else:
            self.picking_deliver_bill = False

    def _compute_picking_deliver(self):
        if self.company_id.stock_picking == True:
            self.picking_deliver = True
        else:
            self.picking_deliver = False

    def _compute_picking_deliver_no(self):
        if self.picking_count > 0:
            self.deliver_no = True
        else:
            self.deliver_no = False

    def _compute_shipment_deliver_no(self):
        if self.picking_shipment_count > 0:
            self.deliver_shipment_no = True
        else:
            self.deliver_shipment_no = False

    def action_stock_transfer(self):
        print('here______________________________')

        for order in self:
            if not order.invoice_line_ids:
                raise UserError(_('Please create some invoice lines.'))
            if not self.name:
                raise UserError(_('Please Validate invoice.'))
            if not self.invoice_picking_id:
                starting_ubigeo = self.company_id.partner_id.l10n_pe_district.code if self.company_id.partner_id.l10n_pe_district else ''
                arrival_ubigeo = self.partner_id.l10n_pe_district.code if self.partner_id.l10n_pe_district else ''
                pick = {
                    'picking_type_id': self.picking_transfer_id.id,
                    'partner_id': self.partner_id.id,
                    'origin': self.name,
                    'location_dest_id': self.partner_id.property_stock_customer.id,
                    'location_id': self.picking_transfer_id.default_location_src_id.id,
                    'l10n_pe_edi_picking_starting_point_state_id': self.company_id.partner_id.state_id.id,
                    'l10n_pe_edi_picking_starting_point_province_id': self.company_id.partner_id.city_id.id,
                    'l10n_pe_edi_picking_starting_point_district_id': self.company_id.partner_id.l10n_pe_district.id,
                    'l10n_pe_edi_picking_starting_point_ubigeo': starting_ubigeo,
                    'l10n_pe_edi_picking_starting_point_street': self.company_id.partner_id.street,
                    'l10n_pe_edi_picking_arrival_point_state_id': self.partner_id.state_id.id,
                    'l10n_pe_edi_picking_arrival_point_province_id': self.partner_id.city_id.id,
                    'l10n_pe_edi_picking_arrival_point_district_id': self.partner_id.l10n_pe_district.id,
                    'l10n_pe_edi_picking_arrival_point_ubigeo': arrival_ubigeo,
                    'l10n_pe_edi_picking_arrival_point_street': self.partner_id.street,
                    'l10n_pe_edi_picking_start_transport_date': self.invoice_date
                }
                picking = self.env['stock.picking'].create(pick)
                self.invoice_picking_id = picking.id
#                 self.picking_count = len(picking)
                moves = order.invoice_line_ids.filtered(lambda r: r.product_id.type in [
                                                        'product', 'consu'])._create_stock_moves_transfer(picking)
                move_ids = moves._action_confirm()
                move_ids._action_assign()
                # picking.button_validate()
                picking.convert_to_epicking()
        # else:
        #	return True
        if self.picking_count > 0:
            picking_type_state = self.env['stock.picking'].search(
                [('origin', '=', self.name), ('state', '!=', 'done')])
            if picking_type_state:
                self.deliver_status = 'partially'
            else:
                self.deliver_status = 'delivered'

#     @api.multi
#     def action_view_picking(self):
#         action = self.env.ref('stock.action_picking_tree_ready')
#         result = action.read()[0]
#         result.pop('id', None)
#         result['context'] = {}
#         result['domain'] = [('id', '=', self.invoice_picking_id.id)]
#         pick_ids = sum([self.invoice_picking_id.id])
#         if pick_ids:
#             res = self.env.ref('stock.view_picking_form', False)
#             result['views'] = [(res and res.id or False, 'form')]
#             result['res_id'] = pick_ids or False
#         return result

    def action_view_picking_delivery(self):
        action = self.env["ir.actions.actions"]._for_xml_id(
            "stock.action_picking_tree_all")
        pickings = self.env['stock.picking'].search(
            [('origin', '=', self.name), ('partner_id', '=', self.partner_id.id)])
        picking = self.env['stock.picking'].browse(self.invoice_picking_id.id)
        if len(pickings) > 1:
            action['domain'] = [('id', 'in', pickings.ids)]
        elif pickings:
            # action['views'] = [(self.env.ref('stock.view_picking_form').id, 'form')]
            form_view = [(self.env.ref('stock.view_picking_form').id, 'form')]
            if 'views' in action:
                action['views'] = form_view + \
                    [(state, view)
                     for state, view in action['views'] if view != 'form']
            else:
                action['views'] = form_view
            action['res_id'] = pickings.id
        return action
        pickings.state = "assigned"

    def action_view_picking_shipment(self):

        # self.env.ref('stock.action_picking_tree_all').read()[0]
        action = self.env["ir.actions.actions"]._for_xml_id(
            "stock.action_picking_tree_all")

        pickings = self.env['stock.picking'].search(
            [('origin', '=', self.name)])
        if len(pickings) > 1:
            action['domain'] = [('id', 'in', pickings.ids)]
        elif pickings:
            # action['views'] = [(self.env.ref('stock.view_picking_form').id, 'form')]
            form_view = [(self.env.ref('stock.view_picking_form').id, 'form')]
            if 'views' in action:
                action['views'] = form_view + \
                    [(state, view)
                     for state, view in action['views'] if view != 'form']
            else:
                action['views'] = form_view
            action['res_id'] = pickings.id
        return action
        pickings.state = "assigned"


class SupplierInvoiceLine(models.Model):
    _inherit = 'account.move.line'

    # @api.multi
    def _create_stock_moves(self, picking):
        moves = self.env['stock.move']
        done = self.env['stock.move'].browse()
        for line in self:
            price_unit = line.price_unit
            template = {
                'name': line.name or '',
                'product_id': line.product_id.id,
                'product_uom': line.product_uom_id.id,
                'location_id': line.move_id.partner_id.property_stock_supplier.id,
                'location_dest_id': picking.picking_type_id.default_location_dest_id.id,
                'picking_id': picking.id,
                # 'move_dest_id': False,
                'state': 'draft',
                'company_id': line.move_id.company_id.id,
                'price_unit': price_unit,
                'picking_type_id': picking.picking_type_id.id,
                # 'procurement_id': False,
                # 'route_ids': 1 and [
                #	(6, 0, [x.id for x in self.env['stock.location.route'].search([('id', 'in', (2, 3))])])] or [],
                'warehouse_id': picking.picking_type_id.warehouse_id.id,
            }
            diff_quantity = line.quantity
            tmp = template.copy()
            tmp.update({
                'product_uom_qty': diff_quantity,
            })
            template['product_uom_qty'] = diff_quantity
            done += moves.create(template)
            print(diff_quantity, "1111")
        return done

    def _create_stock_moves_transfer(self, picking):
        moves = self.env['stock.move']
        done = self.env['stock.move'].browse()
        for line in self:
            price_unit = line.price_unit
            template = {
                'name': line.name or '',
                'product_id': line.product_id.id,
                'product_uom': line.product_uom_id.id,
                'location_id': picking.picking_type_id.default_location_src_id.id,
                'location_dest_id': line.move_id.partner_id.property_stock_customer.id,
                'picking_id': picking.id,
                # 'move_dest_id': False,
                'state': 'draft',
                'company_id': line.move_id.company_id.id,
                'price_unit': price_unit,
                'picking_type_id': picking.picking_type_id.id,
                # 'procurement_id': False,
                # 'route_ids': 1 and [
                #	(6, 0, [x.id for x in self.env['stock.location.route'].search([('id', 'in', (2, 3))])])] or [],
                'warehouse_id': picking.picking_type_id.warehouse_id.id,
            }
            diff_quantity = line.quantity
            tmp = template.copy()
            tmp.update({
                'product_uom_qty': diff_quantity,
            })
            template['product_uom_qty'] = diff_quantity
            done += moves.create(template)
            print(diff_quantity, "22222")
        return done


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    stock_picking = fields.Boolean("Stock Picking From Invoice", related='company_id.stock_picking',
                                   readonly=False, help="Enable Stock Pickings Feature From Customer Invoice")

    stock_picking_bill = fields.Boolean("Stock Picking From Bills", related='company_id.stock_picking_bill',
                                        readonly=False, help="Enable Stock Pickings Feature From Supplier Bills")


class ResCompany(models.Model):
    _inherit = 'res.company'

    stock_picking = fields.Boolean("Stock Picking From Invoice")
    stock_picking_bill = fields.Boolean("Stock Picking From Bills")
