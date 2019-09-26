def choose_parents(num_parents, box_d, box_range):
    mats = [(i, m[1]) for i, m in enumerate(box_range)]
    mats.sort(key=lambda x: x[1])

    # since we are sorted, these are the materials with the highest abs value
    mats = mats[-num_parents:]
    parent_indices = [i for i,m in mats]
    return [box_d[i] for i in parent_indices], [box_range[i] for i in parent_indices], None
