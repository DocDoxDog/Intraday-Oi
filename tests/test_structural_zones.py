from src.multi_expiry import select_structural_nodes


def test_structural_nodes_do_not_follow_every_five_dollars():
    concentrations = [
        (4100.0, -130.0),
        (4110.0, -10.0),
        (4120.0, -15.0),
        (4125.0, -55.0),
        (4130.0, -12.0),
        (4140.0, -20.0),
        (4150.0, -33.0),
        (4160.0, 27.0),
        (4180.0, 16.0),
        (4200.0, 64.0),
        (4225.0, 54.0),
    ]

    supports = select_structural_nodes(
        [(s, v) for s, v in concentrations if v < 0],
        current=4152.8,
        side="DOWN",
    )
    resistances = select_structural_nodes(
        [(s, v) for s, v in concentrations if v > 0],
        current=4152.8,
        side="UP",
    )

    # Only source strikes present in this snapshot may be selected; the
    # absent 4050/4075 levels must not be fabricated from a price ladder.
    assert supports == [4100.0, 4125.0, 4150.0]
    assert 4160.0 in resistances
    assert 4200.0 in resistances
    # The 4225 node is observed but below the configured significance threshold.
    assert 4225.0 not in resistances
    assert resistances == [4160.0, 4200.0]


def test_structural_node_selection_is_magnitude_and_spacing_based():
    concentrations = [(4100.0, -100.0), (4105.0, -95.0), (4110.0, -90.0), (4150.0, -15.0),
                      (4200.0, 80.0), (4205.0, 78.0), (4250.0, 60.0)]
    selected = select_structural_nodes(
        [(s, v) for s, v in concentrations if v > 0],
        current=4180.0,
        side="UP",
    )
    assert selected == [4200.0, 4250.0]


def test_live_style_cfd_normalization_preserves_real_non_five_dollar_nodes():
    futures = 4152.8
    cfd = 4127.56726
    real_futures_nodes = [4150.0, 4160.0, 4200.0, 4225.0]
    cfd_nodes = [round(node - futures + cfd, 5) for node in real_futures_nodes]

    assert cfd_nodes == [4124.76726, 4134.76726, 4174.76726, 4199.76726]
    assert [round(cfd_nodes[i] - cfd_nodes[i - 1], 5) for i in range(1, len(cfd_nodes))] == [10.0, 40.0, 25.0]
