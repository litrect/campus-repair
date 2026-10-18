ACTIVE_STATUSES = frozenset(('CREATED', 'ASSIGNED', 'PROCESSING'))


def effective_overtime(order, now, cancel_time=None):
    if order['is_overtime']:
        return True
    deadline = order['deadline']
    if not deadline:
        return False
    if order['status'] in ACTIVE_STATUSES:
        reference = now
    elif order['status'] == 'CANCELLED':
        reference = cancel_time
    else:
        reference = order['finish_time']
    return bool(reference and reference > deadline)
