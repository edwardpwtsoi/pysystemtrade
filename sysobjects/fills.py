from typing import Union
import datetime
from dataclasses import dataclass
from collections import namedtuple

import pandas as pd

from syscore.constants import named_object
from sysexecution.orders.named_order_objects import missing_order, not_filled
from sysobjects.orders import (
    SimpleOrder,
    ListOfSimpleOrders,
    ListOfSimpleOrdersWithDate,
    SimpleOrderWithDate,
)

from sysexecution.orders.base_orders import Order


@dataclass
class Fill:
    date: datetime.datetime
    qty: int
    price: float
    includes_slippage: bool = False


class ListOfFills(list):
    def __init__(self, list_of_fills):
        list_of_fills = [
            fill for fill in list_of_fills if fill is not (missing_order or not_filled)
        ]
        super().__init__(list_of_fills)

    def _as_dict_of_lists(self) -> dict:
        qty_list = [fill.qty for fill in self]
        price_list = [fill.price for fill in self]
        date_list = [fill.date for fill in self]

        return dict(qty=qty_list, price=price_list, date=date_list)

    def as_pd_df(self) -> pd.DataFrame:
        self_as_dict = self._as_dict_of_lists()
        date_index = self_as_dict.pop("date")
        df = pd.DataFrame(self_as_dict, index=date_index)
        df = df.sort_index()

        return df

    @classmethod
    def from_position_series_and_prices(cls, positions: pd.Series, price: pd.Series):

        list_of_fills = _list_of_fills_from_position_series_and_prices(
            positions=positions, price=price
        )

        return cls(list_of_fills)


def _list_of_fills_from_position_series_and_prices(
    positions: pd.Series, price: pd.Series
) -> ListOfFills:

    (
        trades_without_zeros,
        prices_aligned_to_trades,
    ) = _get_valid_trades_and_aligned_prices(positions=positions, price=price)

    trades_as_list = list(trades_without_zeros.values)
    prices_as_list = list(prices_aligned_to_trades.values)
    dates_as_list = list(prices_aligned_to_trades.index)

    list_of_fills_as_list = [
        Fill(date, qty, price)
        for date, qty, price in zip(dates_as_list, trades_as_list, prices_as_list)
    ]

    list_of_fills = ListOfFills(list_of_fills_as_list)

    return list_of_fills


def _get_valid_trades_and_aligned_prices(
    positions: pd.Series, price: pd.Series
) -> tuple:
    # No delaying done here so we assume positions are already delayed
    trades = positions.diff()
    trades_without_na = trades[~trades.isna()]
    trades_without_zeros = trades_without_na[trades_without_na != 0]

    prices_aligned_to_trades = price.reindex(trades_without_zeros.index, method="ffill")

    return trades_without_zeros, prices_aligned_to_trades


def fill_from_order(order: Order) -> Fill:
    try:
        assert len(order.trade) == 1
    except:
        raise Exception("Can't get fills from multi-leg orders")

    if order.fill_equals_zero():
        return missing_order

    fill_price = order.filled_price
    fill_datetime = order.fill_datetime
    fill_qty = order.fill[0]

    if fill_price is None:
        return missing_order

    if fill_datetime is None:
        return missing_order

    return Fill(fill_datetime, fill_qty, fill_price)


def fill_list_of_simple_orders(
    list_of_orders: ListOfSimpleOrders,
    fill_datetime: datetime.datetime,
    market_price: float,
) -> Fill:
    list_of_fills = [
        fill_from_simple_order(
            simple_order=simple_order,
            fill_datetime=fill_datetime,
            market_price=market_price,
        )
        for simple_order in list_of_orders
    ]
    list_of_fills = ListOfFills(list_of_fills)  ## will remove unfilled

    if len(list_of_fills) == 0:
        return not_filled
    elif len(list_of_fills) == 1:
        return list_of_fills[0]
    else:
        raise Exception(
            "List of orders %s has produced more than one fill %s!"
            % (str(list_of_orders), str(list_of_orders))
        )


def fill_from_simple_order(
    simple_order: SimpleOrder,
    market_price: float,
    fill_datetime: datetime.datetime,
) -> Fill:
    if simple_order.is_zero_order:
        return not_filled

    elif simple_order.is_market_order:
        fill = fill_from_simple_market_order(
            simple_order,
            market_price=market_price,
            fill_datetime=fill_datetime,
        )
    else:
        ## limit order
        fill = fill_from_simple_limit_order(
            simple_order, market_price=market_price, fill_datetime=fill_datetime
        )

    return fill


def fill_from_simple_limit_order(
    simple_order: Union[SimpleOrder, SimpleOrderWithDate],
    market_price: float,
    fill_datetime: datetime.datetime,
) -> Fill:

    limit_price = simple_order.limit_price
    if simple_order.quantity > 0:
        if limit_price > market_price:
            return Fill(
                fill_datetime,
                simple_order.quantity,
                limit_price,
                includes_slippage=True,
            )

    if simple_order.quantity < 0:
        if limit_price < market_price:
            return Fill(
                fill_datetime,
                simple_order.quantity,
                limit_price,
                includes_slippage=True,
            )

    return not_filled


def fill_from_simple_market_order(
    simple_order: Union[SimpleOrder, SimpleOrderWithDate],
    market_price: float,
    fill_datetime: datetime.datetime,
) -> Fill:

    return Fill(
        fill_datetime, simple_order.quantity, market_price, includes_slippage=False
    )
