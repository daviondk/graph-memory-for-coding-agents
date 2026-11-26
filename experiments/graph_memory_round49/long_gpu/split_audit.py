"""Show repository and state overlap between R48, R49 replay and the hardware subset."""
from panel import BASE, D, put, read


def main():
    prior = read(BASE / 'inventory.json.gz')
    current = read(D / 'transfer-inputs.json.gz')
    measured = read(D / 'panel.json')['selected']
    measured_q = {q for c in measured for q in c['seq']}
    measured_projects = {c['repo'] for c in measured}
    prior_projects = {row['repo'] for row in prior.values()}
    current_projects = {row['repo'] for row in current.values()}
    outside = {row['repo'] for q, row in current.items() if q not in measured_q}
    assert measured_q <= current.keys()
    put('split-audit.json', {
        'prior_repositories': sorted(prior_projects),
        'new_repositories': sorted(current_projects),
        'prior_repo_overlap': len(prior_projects & current_projects),
        'prior_state_overlap': len(prior.keys() & current.keys()),
        'full_states': len(current),
        'outside_measured_states': len(current.keys() - measured_q),
        'outside_measured_repo_overlap_with_hardware': len(outside & measured_projects),
    })


if __name__ == '__main__':
    main()

