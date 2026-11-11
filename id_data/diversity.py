"""Synthetic coverage targets, deliberately distinct from medical prevalence."""
import copy
import math
import random

DEFAULTS = {
    'glasses_probability': 0.05,
    'blindness_probability': 0.05,
    'facial_conditions': {
        'cleft_lip': 0.01, 'down_syndrome': 0.01, 'vitiligo': 0.01,
        'alopecia': 0.01, 'facial_palsy': 0.005, 'craniofacial_microsomia': 0.005,
    },
    'cataracts_by_age': {'18_39': 0.002, '40_59': 0.01, '60_74': 0.04, '75_plus': 0.08},
}


def settings(overrides=None):
    result = copy.deepcopy(DEFAULTS)
    for key, value in (overrides or {}).items():
        if key not in result:
            raise ValueError(f'Unknown diversity setting: {key}')
        if isinstance(result[key], dict):
            if not isinstance(value, dict) or set(value) - set(result[key]):
                raise ValueError(f'Invalid diversity settings for {key}')
            result[key].update(value)
        else:
            result[key] = value
    for value in result.values():
        values = value.values() if isinstance(value, dict) else [value]
        for probability in values:
            if isinstance(probability, bool) or not isinstance(probability, (int, float)) or not math.isfinite(probability) or not 0 <= probability <= 1:
                raise ValueError('Diversity probabilities must be finite numbers from 0 to 1')
    if sum(result['facial_conditions'].values()) > 1:
        raise ValueError('Facial condition probabilities must sum to at most 1')
    return result


def apply_facial_condition(sample, rates):
    """One selected profile prevents arbitrary stacking of unrelated diagnoses.

    Generic anatomy is replaced where needed to avoid contradictory instructions.
    These are intended fictional traits, never clinically verified labels.
    """
    roll = random.random()
    selected = 'none'
    for kind, probability in rates.items():
        roll -= probability
        if roll < 0:
            selected = kind
            break
    description = ''
    variant = None
    face, eyes, hair = sample['face'], sample['eyes'], sample['hair']
    if selected == 'cleft_lip':
        variant = random.choices(['repaired_unilateral', 'repaired_bilateral', 'unrepaired_unilateral'], weights=[.7, .2, .1])[0]
        side = random.choice(['left', 'right'])
        mouth = {
            'repaired_unilateral': f'a repaired unilateral cleft lip with a healed scar and slight upper-lip asymmetry on the {side}',
            'repaired_bilateral': 'a repaired bilateral cleft lip with healed upper-lip scars and subtle contour differences',
            'unrepaired_unilateral': f'an unrepaired unilateral cleft lip with a small visible opening on the {side} of the upper lip',
        }[variant]
        hair['facial_hair'] = ''  # Keep the requested lip variation visible.
        face['mouth'] = mouth
        description = f'a person with {mouth}'
    elif selected == 'down_syndrome':
        variant = 'subtle' if random.random() < .5 else 'moderate'
        face['nose'] = f"a low nasal bridge, a softly rounded nose tip, {face['nose_width']}, and {face['nostrils']}"
        eyes['shape'] = 'gently upslanting almond-shaped'
        face['cheeks'] = 'soft midface contours with a slightly flatter nasal root'
        description = f'a person with Down syndrome and {variant} individual facial features'
    elif selected == 'vitiligo':
        variant = random.choice(['around the mouth', 'around the eyes', 'on one cheek and the temple'])
        description = f'a person with vitiligo, with clearly defined depigmented skin patches {variant}'
    elif selected == 'alopecia':
        variant = random.choice(['patchy', 'extensive'])
        if variant == 'extensive':
            hair.update(style='bald', baldness_note='a smooth hairless scalp from extensive alopecia', stray_hair='', facial_hair='', gray_desc='')
            face['brow'] = 'very sparse brows from alopecia'
            description = 'a person with extensive alopecia affecting the scalp and eyebrows'
        else:
            hair['baldness_note'] = 'a visible smooth patch of hair loss near one temple from alopecia'
            description = 'a person with patchy alopecia and a visible hairline patch'
    elif selected == 'facial_palsy':
        variant = random.choice(['left', 'right'])
        face['mouth'] = f'a mouth with subtle resting droop at the {variant} corner'
        face['detail'] = f'mild resting facial asymmetry on the {variant} side'
        sample['metadata']['expression'] = 'a relaxed resting expression'
        description = f'a person with mild residual facial palsy affecting the {variant} side'
    elif selected == 'craniofacial_microsomia':
        variant = random.choice(['left', 'right'])
        face['jaw'] = f'a mildly smaller jaw contour on the {variant} side'
        face['ear'] = f'a smaller outer ear on the {variant} side'
        face['detail'] = f'gentle structural facial asymmetry on the {variant} side'
        description = f'a person with mild craniofacial microsomia affecting the {variant} jaw and ear'
    sample['facial_condition'] = {'type': selected, 'variant': variant, 'description': description,
                                  'label_status': 'intended_synthetic_input'}
