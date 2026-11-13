def walk_answer_tree(node, value_set=None):
    yield node, value_set
    for child in node.get('elements', []):
        yield from walk_answer_tree(child, value_set)
    for value_set in node.get('sets', []):
        for child in value_set.get('elements', []):
            yield from walk_answer_tree(child, value_set)


def get_parent_prefix(set_prefix):
    # compute the parent set from the set_prefix of a set, e.g. '0|1' -> ('0', 1)
    parent_set_prefix, _, parent_set_index = set_prefix.rpartition('|')
    return parent_set_prefix, int(parent_set_index)


def get_child_prefix(value_set):
    # compute the set_prefix for the sets below a set, e.g. ('0', 1) -> '0|1'
    set_prefix, set_index = value_set.get('set_prefix'), value_set.get('set_index')
    return f'{set_prefix}|{set_index}' if set_prefix else str(set_index)


def get_ancestor_sets(set_prefix, set_index):
    # yield the set itself and then all its ancestors, e.g. ('0|1', 2) -> ('0|1', 2), ('0', 1), ('', 0)
    yield set_prefix, set_index
    while set_prefix:
        set_prefix, set_index = get_parent_prefix(set_prefix)
        yield set_prefix, set_index


def is_same_or_descendant_set(value_set, ancestor_set):
    set_prefix, set_index = value_set.get('set_prefix'), value_set.get('set_index')
    ancestor_set_prefix, ancestor_set_index = ancestor_set

    # the ancestor set itself
    if set_prefix == ancestor_set_prefix and set_index == ancestor_set_index:
        return True

    # sets below the ancestor set
    child_set_prefix = f'{ancestor_set_prefix}|{ancestor_set_index}' if ancestor_set_prefix else str(ancestor_set_index)
    return set_prefix == child_set_prefix or set_prefix.startswith(f'{child_set_prefix}|')


def find_question(catalog, attribute):
    return next((question for question in catalog.questions if question.attribute_id == attribute.id), None)


def find_parent(catalog, question):
    return next((element for element in catalog.pages + catalog.questionsets if question in element.elements), None)


def find_set(answer_tree, element, instance):
    element_sets = [
        value_set
        for node, value_set in walk_answer_tree(answer_tree)
        if node.get('model') == element._meta.label_lower and node.get('id') == element.id and value_set is not None
    ]

    # look in the set of the instance first and then move up the ancestors, so that the closest set wins
    for ancestor_set in get_ancestor_sets(instance.set_prefix, instance.set_index):
        for value_set in element_sets:
            if is_same_or_descendant_set(value_set, ancestor_set):
                return value_set

    return None
