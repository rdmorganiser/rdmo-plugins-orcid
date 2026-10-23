def walk_answer_tree(node, value_set=None):
    yield node, value_set
    for child in node.get('elements', []):
        yield from walk_answer_tree(child, node)
    for value_set in node.get('sets', []):
        for child in value_set.get('elements', []):
            yield from walk_answer_tree(child, value_set)


def find_question(catalog, attribute):
    return next((question for question in catalog.questions if question.attribute_id == attribute.id), None)


def find_set(answer_tree, question):
    return next(
        (
            value_set
            for element, value_set in walk_answer_tree(answer_tree)
            if element.get('model') == 'questions.question' and element.get('id') == question.id
        ),
        None,
    )
