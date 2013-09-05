"""
Backported error classes for twisted.
"""
__docformat__ = 'epytext en'

class VerifyError(Exception):
    """Could not verify something that was supposed to be signed.
    """

class PeerVerifyError(VerifyError):
    """The peer rejected our verify error.
    """

class CertificateError(Exception):
    """
    We did not find a certificate where we expected to find one.
    """
