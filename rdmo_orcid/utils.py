def walk_answer_tree(node, value_set=None):
    yield node, value_set
    for child in node.get('elements', []):
        yield from walk_answer_tree(child, value_set)
    for value_set in node.get('sets', []):
        for child in value_set.get('elements', []):
            yield from walk_answer_tree(child, value_set)


def find_question(catalog, attribute):
    return next((question for question in catalog.questions if question.attribute_id == attribute.id), None)


def get_ancestor_sets(set_prefix, set_index):
    # yield the set itself and then all its ancestors, e.g. ('0|1', 2) -> ('0|1', 2), ('0', 1), ('', 0)
    yield set_prefix, set_index
    while set_prefix:
        set_prefix, _, set_index = set_prefix.rpartition('|')
        yield set_prefix, int(set_index)


def is_same_or_descendant_set(value_set, ancestor_set):
    set_prefix, set_index = value_set.get('set_prefix'), value_set.get('set_index')
    ancestor_set_prefix, ancestor_set_index = ancestor_set

    # the ancestor set itself
    if set_prefix == ancestor_set_prefix and set_index == ancestor_set_index:
        return True

    # sets below the ancestor set
    child_set_prefix = f'{ancestor_set_prefix}|{ancestor_set_index}' if ancestor_set_prefix else str(ancestor_set_index)
    return set_prefix == child_set_prefix or set_prefix.startswith(f'{child_set_prefix}|')


def find_set(answer_tree, question, instance):
    question_sets = [
        value_set
        for element, value_set in walk_answer_tree(answer_tree)
        if element.get('model') == 'questions.question' and element.get('id') == question.id and value_set is not None
    ]

    # look in the set of the instance first and then move up the ancestors, so that the closest set wins
    for ancestor_set in get_ancestor_sets(instance.set_prefix, instance.set_index):
        for value_set in question_sets:
            if is_same_or_descendant_set(value_set, ancestor_set):
                return value_set

    return None
