from binance.exceptions import BinanceAPIException

from Bot.OrderEnums import OrderStatus, Side
from Bot.FXConnector import FXConnector
from Bot.Strategy.SmartOrder import SmartOrder
from Bot.Strategy.TradingStrategy import TradingStrategy
from Bot.Target import Target
from Bot.Trade import Trade

class EntryStrategy(TradingStrategy):
    def __init__(self, trade: Trade, fx: FXConnector, trade_updated=None, nested=False, exchange_info=None, balance=None, smart=True):
        super().__init__(trade, fx, trade_updated, nested, exchange_info, balance)

        self.is_smart = smart

        self.smart_order = SmartOrder(self.trade_side() == Side.BUY,
                                      self.trade_target().price,
                                      self.on_smart_buy,
                                      self.trade.entry.sl_threshold,
                                      self.trade.entry.pullback_threshold) \
            if self.is_smart else None

    def execute(self, new_price):
        try:
            if self.is_completed():
                return

            target = self.trade_target()

            if self.validate_all_completed([target]):
                self.logInfo('All Orders are Completed')
                return

            if not self.is_smart and self.validate_all_orders([target]):
                return

            if self.is_smart:
                self.smart_order.price_update(new_price)
            else:
                self.place_orders(
                        [{'price': self.exchange_info.adjust_price(new_price if self.is_smart else target.price),
                          'volume': self.exchange_info.adjust_quanity(target.vol.v),
                          'side': self.side().name,
                          'target': target}])

        except BinanceAPIException as bae:
            self.logError(str(bae))

    def on_smart_buy(self, sl_price):
        t = self.trade_target()
        if t.is_active():
            self.fx.cancel_order(self.symbol(), t.id)
            t.set_canceled()
            self.trigger_target_updated()

        if self.trade_side() == Side.BUY:
            limit = max(sl_price, t.price + self.smart_order.sl_threshold_val)
        else:
            limit = min(sl_price, t.price - self.smart_order.sl_threshold_val)

        order = self.fx.create_stop_order(
            sym=self.symbol(),
            side=self.trade_side().name,
            stop_price=self.exchange_info.adjust_price(sl_price),
            price=self.exchange_info.adjust_price(limit),
            volume=self.exchange_info.adjust_quanity(t.vol.v)
        )

        t.set_active(order['orderId'])
        self.trigger_target_updated()

    def trade_side(self):
        if self.trade.entry.side:
            return self.trade.entry.side

        return Side.BUY if self.trade.side == Side.SELL else Side.SELL

    def is_completed(self):
        return self.trade.entry.target.is_completed()

    def trade_target(self):
        return self.trade.entry.target

    def validate_all_orders(self, targets):
        return all(t.status == OrderStatus.ACTIVE or t.has_id() for t in targets)

    def validate_all_completed(self, targets):
        return all(t.status == OrderStatus.COMPLETED for t in targets)

    def place_orders(self, allocations):
        for a in allocations:
            target = a.pop('target', None)

            if self.is_smart:
                a.pop('price', None)
                order = self.fx.create_makret_order(sym=self.symbol(), **a)
            else:
                order = self.fx.create_limit_order(sym=self.symbol(), **a)

            target.set_active(order['orderId'])
        self.trigger_target_updated()

    def order_status_changed(self, t: Target, data):
        if not t.is_entry_target():
            return

        if t.is_completed():
            self.logInfo('Target {} completed'.format(t))
        else:
            self.logInfo('Order status updated: {}'.format(t.status))




