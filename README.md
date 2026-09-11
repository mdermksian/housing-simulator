# Housing Simulator

This housing simulator compares costs between renting for a duration, and purchasing a house. The goal of the simulation is to, over a set period of time, forecast out what the financial impact of buying a house is as compared to simply renting. It tries to account for the fact that a certain amount of starting capital would be held in savings and investment accounts, and would accrue gains over time. It can also incorporate recurring costs which are often overlooked in comparisons like this: maintenance costs, utilities costs, etc.

Once a user configures the simulation, the app runs the simulation out to a configured time duration, stepping the simulation at the necessary interval and storing the state of the simulation such that it can be plotted at the end.

## Technology

The simulation should use python for its underlying logic, and eventually Slint for rendering the UI, which will allow a user to configure the simulation, run it, and view the results.