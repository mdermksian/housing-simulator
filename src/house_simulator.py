from dataclasses import dataclass

# Renting


@dataclass(frozen=True)
class RentConfig:
    rent: float  # US dollars per month
    utilities: float  # US dollars per month
    insurance: float  # US dollars per month
    annual_increase: float  # percentage increase per year


# Buying


@dataclass(frozen=True)
class MortgagePolicy:
    principal: float  # US dollars
    interest_rate: float  # annual interest rate as a decimal
    term_years: int  # number of years for the mortgage


@dataclass(frozen=True)
class BuyConfig:
    mortgage: MortgagePolicy
    down_payment: float  # US dollars
    property_tax: float  # US dollars per month
    utilities: float  # US dollars per month
    maintenance: float  # US dollars per month
    insurance: float  # US dollars per month


# Income and Investment


@dataclass(frozen=True)
class InvestmentPolicy:
    monthly_return: float  # expected monthly return as a decimal
    percentage_invested: float  # percentage of savings invested in the market


@dataclass(frozen=True)
class InitialConditions:
    savings: float  # US dollars
    keep_on_hand: float  # US dollars
    salary: float  # US dollars per year


@dataclass(frozen=True)
class SimConfig:
    rent_config: RentConfig
    buy_config: BuyConfig
    initial_conditions: InitialConditions
    duration_years: int  # number of years to simulate


class HouseSimulator:
    CONFIG = SimConfig(
        rent_config=RentConfig(
            rent=3000.0, utilities=300.0, insurance=100.0, annual_increase=3.0
        ),
        buy_config=BuyConfig(
            mortgage=MortgagePolicy(
                principal=500000.0, interest_rate=0.0658, term_years=30
            ),
            down_payment=100000.0,
            property_tax=150.0,
            utilities=200.0,
            maintenance=100.0,
            insurance=150.0,
        ),
        initial_conditions=InitialConditions(
            savings=10000.0, keep_on_hand=5000.0, salary=75000.0
        ),
        duration_years=15,
    )

    def run(self):
        # Placeholder for simulation logic
        pass
