
def choose_parents(num_parents, box_d, box_range):
    """
    select the best performing materials from the prior generation only. This algorithm was
    implemented in order to test a "reverse-best" pathway of starting with an ordered structure like
    a perfect cubic 2x2x2 grid, and seeing how many generations of declining V/V materials are
    mutated until the statistics make it possible for improved materials to be generated again.
    """
    # get all the materials in the most recent generation of num_parents
    mats = [(i, m[1]) for i, m in enumerate(box_range[-num_parents:])]

    # get best performing parent
    mats.sort(key=lambda x: x[1])
    index = mats[-1][0]
    return [box_d[index] for _ in range(num_parents)], [box_range[index] for _ in range(num_parents)], None
